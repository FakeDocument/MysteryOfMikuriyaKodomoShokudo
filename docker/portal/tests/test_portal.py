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
        response = asyncio.run(main.search(self.request({'keyword': '%', 'owner': 'records', 'scope': '非公開'}, cookie=cookie)))
        self.assertNotIn('transfer-settings', response.body.decode())
        with self.assertRaises(HTTPException) as error:
            main.document(self.request(cookie=cookie), 'transfer-settings')
        self.assertEqual(error.exception.status_code, 404)

    def test_catalog_does_not_show_documents_before_search(self):
        cookie = self.login()
        landing = main.index(self.request(cookie=cookie))
        self.assertNotIn('results-panel', landing.body.decode())

        restored_search = main.index(self.request(query={'keyword': ''}, cookie=cookie))
        self.assertIn('results-panel', restored_search.body.decode())

    def test_one_injection_reveals_restricted_documents(self):
        cookie = self.login()
        payload = "' OR 1=1 -- "
        rows = main.search_documents(payload, 'katayanagi')
        self.assertEqual(len(rows), 19)
        self.assertEqual({row['slug'] for row in rows if row['owner'] == 'records'},
                         {'a07-observation', 'folklore', 'mikuriya-interview', 'a07-policy', 'transfer-settings'})
        page = main.document(self.request(query={'keyword': payload}, cookie=cookie), 'transfer-settings')
        self.assertEqual(page.status_code, 200)

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

    def test_framework_documentation_routes_are_disabled(self):
        paths = {route.path for route in main.app.routes}
        self.assertTrue(paths.isdisjoint({'/docs', '/redoc', '/openapi.json'}))


if __name__ == '__main__':
    unittest.main()
