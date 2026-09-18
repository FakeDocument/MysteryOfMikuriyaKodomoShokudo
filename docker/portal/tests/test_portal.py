import asyncio
import tempfile
import unittest
from http.cookies import SimpleCookie
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from fastapi import HTTPException, Request
from app import main


class PortalTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_patch = patch.object(main, 'DB_PATH', Path(self.temp.name) / 'documents.db')
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        main.initialize_database()

    def request(self, form=None, query=None, cookie='', catalog=True):
        headers = [(b'cookie', cookie.encode())]
        if catalog:
            headers.append((b'x-kaiiki-service', b'catalog'))
        async def receive():
            return {'type': 'http.request', 'body': urlencode(form or {}).encode(), 'more_body': False}
        return Request({'type': 'http', 'method': 'POST', 'path': '/', 'headers': headers,
                        'query_string': urlencode(query or {}).encode()}, receive)

    def login(self):
        response = asyncio.run(main.login(self.request({'code': 'E6N4-P9R2-T3M5'})))
        self.assertEqual(response.status_code, 303)
        cookie = SimpleCookie(response.headers['set-cookie'])
        return f'{main.SESSION_COOKIE}={cookie[main.SESSION_COOKIE].value}'

    def test_migration_code_is_required_and_password_formula_no_longer_works(self):
        self.assertEqual(main.redeem_code('E6N4-P9R2-T3M5'), 'katayanagi')
        for code in ('e6n4-p9r2-t3m5', "' OR 1=1 -- ", 'Katayanagi2021', ''):
            self.assertIsNone(main.redeem_code(code))
        response = asyncio.run(main.login(self.request({'username': 'katayanagi', 'password': 'Katayanagi2021'})))
        self.assertEqual(response.status_code, 401)
        self.assertNotIn('set-cookie', response.headers)

    def test_no_search_or_document_access_without_login(self):
        with self.assertRaises(HTTPException) as error:
            asyncio.run(main.search(self.request({'keyword': "' OR 1=1 -- "})))
        self.assertEqual(error.exception.status_code, 401)
        with self.assertRaises(HTTPException):
            main.document(self.request(query={'keyword': "' OR 1=1 -- "}), 'transfer-settings')
        page = main.index(self.request())
        self.assertIn('閲覧コード', page.body.decode())
        self.assertNotIn('hozen_sync', page.body.decode())

    def test_normal_search_cannot_choose_another_owner(self):
        cookie = self.login()
        rows = main.search_documents('', 'katayanagi')
        self.assertEqual(len(rows), 14)
        self.assertTrue(all(row['owner'] in ('common', 'katayanagi') for row in rows))
        self.assertEqual(main.search_documents('出力', 'katayanagi'), [])
        response = asyncio.run(main.search(self.request({'keyword': '%', 'owner': 'records', 'scope': '非公開'}, cookie=cookie)))
        self.assertNotIn('transfer-settings', response.body.decode())
        with self.assertRaises(HTTPException) as error:
            main.document(self.request(cookie=cookie), 'transfer-settings')
        self.assertEqual(error.exception.status_code, 404)

    def test_one_injection_reveals_documents_and_smb_pivot(self):
        cookie = self.login()
        payload = "' OR 1=1 -- "
        rows = main.search_documents(payload, 'katayanagi')
        self.assertEqual(len(rows), 18)
        self.assertEqual({row['slug'] for row in rows if row['owner'] == 'records'},
                         {'a07-observation', 'folklore', 'a07-policy', 'transfer-settings'})
        page = main.document(self.request(query={'keyword': payload}, cookie=cookie), 'transfer-settings')
        self.assertIn('hozen_sync', page.body.decode())
        self.assertIn('TideLog_2024', page.body.decode())
        # SQLで全件を持ち出しても、引き渡し原簿はこのDBにはない。
        self.assertNotIn('25:00', ''.join(row['body'] for row in rows))
        self.assertNotIn('荷捌き所', ''.join(row['body'] for row in rows))

    def test_logout_revokes_session(self):
        cookie = self.login()
        main.logout(self.request(cookie=cookie))
        self.assertIsNone(main.current_user(self.request(cookie=cookie)))

    def test_public_service_cannot_be_used_as_catalog(self):
        cookie = self.login()
        with self.assertRaises(HTTPException) as error:
            asyncio.run(main.search(self.request({'keyword': "' OR 1=1 -- "}, cookie=cookie, catalog=False)))
        self.assertEqual(error.exception.status_code, 404)
        with self.assertRaises(HTTPException):
            main.archive(self.request(cookie=cookie))

    def test_guest_handover_contains_code_but_public_pages_do_not(self):
        templates = Path(__file__).parents[1] / 'app/templates'
        public = (templates / 'public.html').read_text()
        archive = (templates / 'archive.html').read_text()
        handover = Path(__file__).parents[1] / 'samba/handover/catalog/seat-03.txt'
        self.assertNotIn(main.MIGRATION_CODE, public + archive)
        self.assertNotIn('初期パスワード', public + archive)
        self.assertIn(main.MIGRATION_CODE, handover.read_text())
        smb_config = (Path(__file__).parents[1] / 'samba/smb.conf').read_text()
        self.assertIn('[handover]', smb_config)
        self.assertIn('guest ok = yes', smb_config)
        self.assertIn('valid users = hozen_sync', smb_config)

    def test_smb_records_need_cross_reference_and_are_read_only(self):
        root = Path(__file__).parents[1] / 'samba'
        intake = (root / 'share/01_transport/intake.txt').read_text()
        dispatch = (root / 'share/01_transport/dispatch.txt').read_text()
        entrances = (root / 'share/02_site/entrances.txt').read_text()
        self.assertIn('9月2日 | 12歳', intake)
        self.assertIn('R-14 | 2026年9月10日 | 25:00 | M-2 | 確定', dispatch)
        self.assertIn('M-2：裏手の荷捌き所', entrances)
        self.assertIn('read only = yes', (root / 'smb.conf').read_text())
        mail = Path(__file__).parents[2] / 'sushi/webmail/app.py'
        self.assertIn('佐々木笑真、12歳。9月2日', mail.read_text())
        for body in (intake, dispatch, entrances):
            self.assertNotIn('佐々木笑真', body)
            self.assertFalse('25:00' in body and '荷捌き所' in body)

    def test_framework_documentation_routes_are_disabled(self):
        paths = {route.path for route in main.app.routes}
        self.assertTrue(paths.isdisjoint({'/docs', '/redoc', '/openapi.json'}))


if __name__ == '__main__':
    unittest.main()
