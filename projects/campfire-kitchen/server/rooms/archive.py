"""One-way GitHub archive worker. Lease + create-only content + remote byte verification.

Execute periodically with systemd; room expiry never depends on this worker running.
Only this process receives GitHub credentials. API routes cannot read archive storage.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import logging
import os
import re
from pathlib import Path
from urllib.parse import quote
import httpx
from .domain import digest
from .store import Store

LOG = logging.getLogger('campfire.archive')


class ArchiveError(Exception):
    pass


class GitHubSink:
    def __init__(self, repository: str, branch: str, token: str, client=None):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
            raise ValueError('Invalid archive repository')
        if branch in ('main', 'master', 'chat') or not re.fullmatch(r'[A-Za-z0-9_/-]+', branch):
            raise ValueError('Use a dedicated, pre-created archive branch')
        if not token.strip():
            raise ValueError('Archive credential is empty')
        self.repository, self.branch = repository, branch
        self.client = client or httpx.Client(base_url='https://api.github.com', timeout=25, follow_redirects=False)
        self.headers = {'Authorization': 'Bearer ' + token.strip(), 'Accept': 'application/vnd.github+json',
                        'X-GitHub-Api-Version': '2026-03-10', 'User-Agent': 'campfire-room-archive/1'}

    def request(self, method, path, **kwargs):
        try:
            response = self.client.request(method, f'/repos/{self.repository}/' + path, headers=self.headers, **kwargs)
        except httpx.HTTPError:
            raise ArchiveError('GITHUB_NETWORK') from None
        if response.status_code not in (200, 201, 404, 409, 422):
            raise ArchiveError(f'GITHUB_HTTP_{response.status_code}')
        return response

    def preflight(self):
        response = self.request('GET', 'git/ref/heads/' + quote(self.branch, safe=''))
        if response.status_code != 200:
            raise ArchiveError('ARCHIVE_BRANCH_MISSING')
        probe = '{"application":"campfire-room-archives","protocol":1}\n'
        self.put({'room_id':'archive-probe-v1','path':'system/archive-probe-v1.json',
                  'payload':probe,'hash':digest(probe)})

    def _existing(self, path):
        response = self.request('GET', 'contents/' + quote(path, safe='/'), params={'ref': self.branch})
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise ArchiveError('GITHUB_READ_CONFLICT')
        value = response.json()
        if value.get('type') != 'file' or value.get('encoding') != 'base64':
            raise ArchiveError('GITHUB_CONTENT_FORMAT')
        try:
            binary = base64.b64decode(''.join(value['content'].split()), validate=True)
        except (ValueError, KeyError):
            raise ArchiveError('GITHUB_CONTENT_FORMAT') from None
        return binary, value.get('sha', '')

    def put(self, job: dict) -> tuple[str, str]:
        payload = job['payload'].encode('utf-8')
        if digest(job['payload']) != job['hash']:
            raise ArchiveError('LOCAL_ARCHIVE_HASH_MISMATCH')
        expected_blob = hashlib.sha1(b'blob ' + str(len(payload)).encode() + b'\0' + payload).hexdigest()
        existing, commit_sha = self._existing(job['path']), None
        if existing is None:
            response = self.request('PUT', 'contents/' + quote(job['path'], safe='/'), json={
                'branch': self.branch, 'message': 'archive: closed campfire room ' + job['room_id'],
                'content': base64.b64encode(payload).decode('ascii'),
            })
            if response.status_code not in (201, 409, 422):
                raise ArchiveError('GITHUB_CREATE_FAILED')
            if response.status_code == 201:
                commit_sha = response.json().get('commit', {}).get('sha')
            existing = self._existing(job['path'])
        if existing is None or existing[0] != payload or existing[1] != expected_blob:
            raise ArchiveError('REMOTE_ARCHIVE_MISMATCH')
        if not commit_sha:
            # After an uncertain acknowledgement, verify the existing immutable file and its commit.
            response = self.request('GET', 'commits', params={'sha': self.branch, 'path': job['path'], 'per_page': 1})
            commits = response.json() if response.status_code == 200 else []
            if not isinstance(commits, list) or not commits:
                raise ArchiveError('GITHUB_COMMIT_MISSING')
            commit_sha = commits[0].get('sha')
        if not isinstance(commit_sha, str) or re.fullmatch(r'[0-9a-f]{40}', commit_sha) is None:
            raise ArchiveError('GITHUB_COMMIT_INVALID')
        return commit_sha, expected_blob


def run_once(store: Store, sink: GitHubSink, budget: int = 100) -> dict:
    closed = store.freeze_expired()
    succeeded, failed = 0, 0
    try:
        sink.preflight()
    except (ArchiveError, ValueError, KeyError):
        LOG.error('archive_preflight_failed')
        return {'closed': closed, 'succeeded': 0, 'failed': 1, **store.archive_health()}
    for _ in range(budget):
        job = store.claim_archive()
        if job is None:
            break
        try:
            commit, blob = sink.put(job)
            succeeded += int(store.finish_archive(job, commit, blob))
        except Exception as error:
            reason = str(error) if isinstance(error, ArchiveError) else 'ARCHIVE_INTERNAL_ERROR'
            store.fail_archive(job, reason)
            failed += 1
            LOG.error('archive_job_failed code=%s', reason)
    health = store.archive_health()
    if failed == 0 and health['failedJobs'] == 0:
        store.mark_archiver_ok()
    return {'closed': closed, 'succeeded': succeeded, 'failed': failed, **health}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--health', action='store_true')
    args = parser.parse_args()
    store = Store(os.environ['ROOMS_DATABASE'])
    if args.health:
        result = store.archive_health()
    else:
        credential = Path(os.environ['CREDENTIALS_DIRECTORY']) / 'github_token'
        sink = GitHubSink(os.environ['ROOMS_ARCHIVE_REPOSITORY'], os.environ['ROOMS_ARCHIVE_BRANCH'], credential.read_text().strip())
        try:
            result = run_once(store, sink)
        finally:
            sink.client.close()
    print(json.dumps(result, sort_keys=True))
    return int(result.get('failed', 0) > 0 or result['overdueSeconds'] > 3600 or result['unswept'] > 0)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
