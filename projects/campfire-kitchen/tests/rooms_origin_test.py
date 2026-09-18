import unittest
from starlette.testclient import TestClient
from server.rooms.api import create_app


class StubStore:
    def archiver_ready(self):
        return True

    def session(self, token):
        return 'x' * 43


class RoomOriginTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            StubStore(),
            'https://furrypant.com,https://www.furrypant.com',
            secure=True,
            require_archiver=True,
        )

    def session(self, origin):
        with TestClient(self.app, base_url=origin) as client:
            return client.post(
                '/api/rooms/session',
                json={},
                headers={
                    'Origin': origin,
                    'X-Room-Client': '1',
                    'Sec-Fetch-Site': 'same-origin',
                },
            )

    def test_apex_and_www_are_both_explicitly_allowed(self):
        for origin in ('https://furrypant.com', 'https://www.furrypant.com'):
            with self.subTest(origin=origin):
                response = self.session(origin)
                self.assertEqual(response.status_code, 200)
                cookie = response.headers.get('set-cookie', '')
                self.assertIn('__Host-campfire-device=', cookie)
                self.assertIn('HttpOnly', cookie)
                self.assertIn('Secure', cookie)
                self.assertIn('SameSite=strict', cookie)

    def test_unlisted_host_is_rejected_even_for_health(self):
        with TestClient(self.app, base_url='https://evil.example') as client:
            response = client.get('/api/rooms/health')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error']['code'], 'ORIGIN')

    def test_unlisted_mutation_origin_is_rejected(self):
        with TestClient(self.app, base_url='https://furrypant.com') as client:
            response = client.post(
                '/api/rooms/session',
                json={},
                headers={
                    'Origin': 'https://evil.example',
                    'X-Room-Client': '1',
                    'Sec-Fetch-Site': 'same-origin',
                },
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error']['code'], 'ORIGIN')

    def test_duplicate_or_non_https_production_origins_fail_at_startup(self):
        with self.assertRaises(ValueError):
            create_app(StubStore(), 'https://furrypant.com,https://furrypant.com')
        with self.assertRaises(ValueError):
            create_app(StubStore(), 'http://furrypant.com')


if __name__ == '__main__':
    unittest.main()
