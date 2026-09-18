from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from stage_a_redo.publish import publish, verified_files, PREFIX

def run(*args: str, cwd: Path | None = None) -> str:
    r = subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True, timeout=30)
    return r.stdout.strip()

with tempfile.TemporaryDirectory(prefix='stage-a-publish-local-test-') as root:
    root = Path(root)
    origin = root / 'origin.git'
    client = root / 'client'
    run('git', 'init', '--bare', str(origin))
    run('git', 'init', str(client))
    run('git', 'config', 'user.name', 'Local validation', cwd=client)
    run('git', 'config', 'user.email', 'validation@example.invalid', cwd=client)
    run('git', 'remote', 'add', 'origin', str(origin), cwd=client)
    (client/'README.md').write_text('unrelated project content must remain unchanged\n')
    run('git', 'add', 'README.md', cwd=client)
    run('git', 'commit', '-m', 'local fixture', cwd=client)
    branch = 'gpt/20260918-token-audit'
    run('git', 'push', 'origin', 'HEAD:refs/heads/'+branch, cwd=client)
    original_head = run('git', 'rev-parse', 'HEAD', cwd=client)
    original_index = (client/'.git/index').read_bytes()
    (client/'untracked.txt').write_text('private worktree remains untouched\n')
    before_status = run('git', 'status', '--porcelain', cwd=client)
    first = publish(client, branch)
    assert first['status'] == 'PUBLISHED_VERIFIED_NOT_DEPLOYED', first
    second = publish(client, branch)
    assert second['status'] == 'ALREADY_PUBLISHED_VERIFIED', second
    assert original_head == run('git', 'rev-parse', 'HEAD', cwd=client)
    assert original_index == (client/'.git/index').read_bytes()
    assert before_status == run('git', 'status', '--porcelain', cwd=client)
    files = verified_files()
    commit = first['commit']
    for name, data in files.items():
        actual = subprocess.run(['git', '-C', str(origin), 'show', commit+':'+PREFIX+name], capture_output=True, check=True).stdout
        assert actual == data, name
    assert run('git', '-C', str(origin), 'show', commit+':README.md') == 'unrelated project content must remain unchanged'
    refs = run('git', 'for-each-ref', '--format=%(refname)', 'refs/stage-a-publish/', cwd=client)
    assert not refs, refs
    result = {'status':'PASS', 'environment':'isolated local Git bare repository, no network',
              'python':sys.version.split()[0], 'checks':[
                  'one multi-file commit published and every remote file read back byte-for-byte',
                  'second identical publication was idempotent with no new commit',
                  'existing worktree HEAD/index/untracked content preserved',
                  'unrelated repository content preserved',
                  'temporary private ref cleaned'],
              'files_verified':len(files), 'github_cloud_publication_tested':False}
    print(json.dumps(result, indent=2))

