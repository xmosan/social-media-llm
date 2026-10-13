"""Owner-only OAuth/boards with synthetic provider responses, no live tokens."""
from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs,urlsplit
from unittest.mock import Mock,patch
import base64,json
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware
from app.config import settings
from app.db import get_db
from app.models import Org,User,OrgMember,PinterestConnection as Connection,PinterestConnectionAttempt as Attempt
from app.routes import pinterest
from app.security.auth import get_current_user
from app.services import pinterest_connection as service
from app.services.channels.pinterest import PinterestError
from test_security import DatabaseCase

ORIGIN='https://app.sabeelstudio.com'
TOKENS={'access_token':'synthetic-access','refresh_token':'synthetic-refresh','expires_in':3600,'scope':'synthetic'}
BOARD={'id':'123','name':'Fixture reminders','privacy':'PUBLIC','owner':{'username':'fixture'}}


class PinterestConnectionTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        Connection.__table__.create(self.engine);Attempt.__table__.create(self.engine)
        self.db.add_all([Org(id=1,name='Own'),Org(id=2,name='Other')]);self.db.flush()
        self.user=User(id=1,email='owner@fixture.test',is_active=True,is_superadmin=True,active_org_id=1)
        self.db.add(self.user);self.db.flush();self.db.add(OrgMember(user_id=1,org_id=1,role='owner'));self.db.commit()
        self.api=Mock(sandbox=True)
        self.api.authorization_url.side_effect=lambda state:ORIGIN+'/provider?state='+state
        self.api.exchange_code.return_value=TOKENS.copy();self.api.account.return_value={'username':'fixture'}
        self.api.refresh.return_value={**TOKENS,'access_token':'synthetic-new','refresh_token':'synthetic-rotated'}
        self.api.boards.return_value={'items':[BOARD],'bookmark':None};self.api.board.return_value=BOARD
        for patcher in (patch.object(service,'client',return_value=self.api),patch.object(pinterest,'check_auth_attempt'),
                        patch.object(settings,'platform_owner_email',self.user.email),patch.object(settings,'pinterest_client_id','fixture'),
                        patch.object(settings,'pinterest_client_secret','synthetic-secret'),patch.object(settings,'pinterest_sandbox',True)):
            patcher.start();self.addCleanup(patcher.stop)
        app=FastAPI();app.include_router(pinterest.router)
        app.add_middleware(SessionMiddleware,secret_key=settings.secret_key,https_only=True,same_site='lax')
        app.dependency_overrides[get_db]=lambda:self.db;app.dependency_overrides[get_current_user]=lambda:self.user
        self.client=TestClient(app,base_url=ORIGIN,follow_redirects=False);self.addCleanup(self.client.close)

    def start(self):
        r=self.client.post('/auth/pinterest/login',headers={'Origin':ORIGIN});self.assertEqual(r.status_code,303,r.text)
        return parse_qs(urlsplit(r.headers['location']).query)['state'][0]

    def connect(self):
        state=self.start();r=self.client.get('/auth/pinterest/callback',params={'code':'fixture','state':state})
        self.assertEqual(r.status_code,303,r.text);self.assertTrue(r.headers['location'].endswith('connected'));return state

    def test_happy_path_encrypted_storage_cookie_and_no_publication(self):
        state=self.start()
        session=json.loads(base64.b64decode(self.client.cookies.get('session').split('.')[0]))
        self.assertEqual(set(session),{'pinterest_connection'});self.assertNotIn(state,str(session))
        r=self.client.get('/auth/pinterest/callback',params={'code':'fixture','state':state})
        self.assertEqual(r.status_code,303)
        row=self.db.query(Connection).one();self.assertNotIn('synthetic-access',row.encrypted_tokens)
        self.assertEqual(service.decrypt(row),TOKENS);self.assertTrue(row.active);self.assertTrue(row.sandbox)
        self.assertEqual(self.db.query(Attempt).count(),0)
        page=self.client.get(pinterest.HOME);self.assertEqual(page.status_code,200)
        self.assertNotIn('synthetic-access',page.text);self.assertEqual(page.headers['cache-control'],'no-store')
        self.assertIn('Carousels, Stories and Pinterest scheduling are not enabled',page.text);self.api.create_pin.assert_not_called()

    def test_owner_guard_and_origin_are_required_on_all_entry_points(self):
        self.assertEqual(self.client.post('/auth/pinterest/login').status_code,403)
        self.user.is_superadmin=False
        for method,path in [('get',pinterest.HOME),('post','/auth/pinterest/login'),('get','/auth/pinterest/callback'),
                            ('get','/api/pinterest/boards'),('post','/api/pinterest/board'),('post','/api/pinterest/sandbox-board'),('post','/auth/pinterest/disconnect')]:
            self.assertEqual(getattr(self.client,method)(path).status_code,403)
        self.api.exchange_code.assert_not_called()

    def test_form_page_preserves_same_origin_without_external_referrers(self):
        page=self.client.get(pinterest.HOME)
        self.assertEqual(page.status_code,200)
        self.assertEqual(page.headers['referrer-policy'],'same-origin')
        self.assertEqual(page.headers['cache-control'],'no-store')
        self.assertEqual(page.headers['x-frame-options'],'DENY')
        self.assertIn('method="post" action="/auth/pinterest/login"',page.text)
        self.client.cookies.set('access_token','synthetic-owner-session')
        response=self.client.post('/auth/pinterest/login',headers={'Origin':ORIGIN})
        self.assertEqual(response.status_code,303)
        self.assertEqual(response.headers['referrer-policy'],'no-referrer')

    def test_cookie_authenticated_forms_still_reject_untrusted_origins(self):
        self.client.cookies.set('access_token','synthetic-owner-session')
        for origin in (None,'null','https://untrusted.test',ORIGIN+'.untrusted.test'):
            headers={} if origin is None else {'Origin':origin}
            for path in ('/auth/pinterest/login','/auth/pinterest/disconnect','/api/pinterest/board'):
                with self.subTest(origin=origin,path=path):
                    response=self.client.post(path,headers=headers,json={'board_id':'123'})
                    self.assertEqual(response.status_code,403)
        self.assertEqual(self.db.query(Attempt).count(),0)
        self.api.authorization_url.assert_not_called()
        self.api.exchange_code.assert_not_called()

    def test_callback_and_disconnect_keep_no_referrer_policy(self):
        self.client.cookies.set('access_token','synthetic-owner-session')
        state=self.start()
        response=self.client.get('/auth/pinterest/callback',params={'code':'fixture','state':state})
        self.assertEqual(response.status_code,303)
        self.assertEqual(response.headers['referrer-policy'],'no-referrer')
        response=self.client.post('/auth/pinterest/disconnect',headers={'Origin':ORIGIN})
        self.assertEqual(response.status_code,303)
        self.assertEqual(response.headers['referrer-policy'],'no-referrer')

    def test_bad_cross_browser_replayed_or_expired_state_never_exchanges(self):
        state=self.start()
        self.assertEqual(self.client.get('/auth/pinterest/callback',params={'state':'x'*43,'code':'fixture'}).status_code,400)
        self.api.exchange_code.assert_not_called()
        self.client.get('/auth/pinterest/callback',params={'state':state,'code':'fixture'})
        self.assertEqual(self.client.get('/auth/pinterest/callback',params={'state':state,'code':'fixture'}).status_code,401)
        self.assertEqual(self.api.exchange_code.call_count,1)
        state=self.start();self.client.cookies.clear()
        self.assertEqual(self.client.get('/auth/pinterest/callback',params={'state':state,'code':'fixture'}).status_code,401)
        state=self.start();row=self.db.query(Attempt).one();row.expires_at=service.utcnow()-timedelta(seconds=1);self.db.commit()
        self.assertEqual(self.client.get('/auth/pinterest/callback',params={'state':state,'code':'fixture'}).status_code,400)

    def test_workspace_switch_and_cancel_preserve_previous_connection(self):
        self.connect();state=self.start();self.user.active_org_id=2;self.db.commit()
        self.assertEqual(self.client.get('/auth/pinterest/callback',params={'state':state,'code':'fixture'}).status_code,400)
        self.user.active_org_id=1;self.db.commit()
        r=self.client.get('/auth/pinterest/callback',params={'state':state,'error':'denied'})
        self.assertTrue(r.headers['location'].endswith('cancelled'));self.assertTrue(self.db.query(Connection).one().active)

    def test_provider_failure_does_not_leak_or_replace_connection(self):
        self.connect();old=self.db.query(Connection).one().encrypted_tokens
        self.api.exchange_code.side_effect=RuntimeError('private-secret')
        state=self.start();r=self.client.get('/auth/pinterest/callback',params={'state':state,'code':'fixture'})
        self.assertNotIn('private-secret',r.text);self.assertTrue(r.headers['location'].endswith('unavailable'))
        self.assertEqual(self.db.query(Connection).one().encrypted_tokens,old)

    def test_select_verifies_ownership_privacy_and_persists_separately(self):
        self.connect();self.api.boards.return_value={'items':[BOARD,{**BOARD,'id':'456','owner':{'username':'other'}}],'bookmark':'next'}
        r=self.client.get('/api/pinterest/boards');self.assertEqual(r.json(),{'items':[{'id':'123','name':'Fixture reminders'}],'bookmark':'next'})
        for board in ({**BOARD,'privacy':'SECRET'},{**BOARD,'owner':{'username':'other'}},{**BOARD,'id':'999'}):
            self.api.board.return_value=board
            self.assertEqual(self.client.post('/api/pinterest/board',json={'board_id':'123'},headers={'Origin':ORIGIN}).status_code,422)
        self.api.board.return_value=BOARD
        self.assertEqual(self.client.post('/api/pinterest/board',json={'board_id':'123'},headers={'Origin':ORIGIN}).status_code,200)
        self.assertEqual(self.db.query(Connection).one().board_id,'123');self.api.create_pin.assert_not_called()

    def test_refresh_rotates_encrypted_token_and_unknown_refresh_requires_reconnect(self):
        self.connect();row=self.db.query(Connection).one();row.expires_at=service.utcnow();self.db.commit()
        self.assertEqual(self.client.get('/api/pinterest/boards').status_code,200)
        self.assertEqual(service.decrypt(row)['refresh_token'],'synthetic-rotated');self.api.refresh.assert_called_once_with('synthetic-refresh')
        row.expires_at=service.utcnow();self.db.commit();self.api.refresh.side_effect=PinterestError('unavailable')
        self.assertEqual(self.client.get('/api/pinterest/boards').status_code,422)
        self.db.refresh(row);self.assertFalse(row.active);self.assertIsNone(row.encrypted_tokens)

    def test_disconnect_consumes_pending_callback_and_forgets_local_credentials(self):
        self.connect();state=self.start()
        self.assertEqual(self.client.post('/auth/pinterest/disconnect',headers={'Origin':ORIGIN}).status_code,303)
        row=self.db.query(Connection).one();self.assertFalse(row.active);self.assertIsNone(row.encrypted_tokens)
        self.assertEqual(self.db.query(Attempt).count(),0)
        self.assertEqual(self.client.get('/auth/pinterest/callback',params={'state':state,'code':'fixture'}).status_code,401)

    def test_interrupted_refresh_cannot_reuse_consumed_token(self):
        self.connect();row=self.db.query(Connection).one();row.expires_at=service.utcnow();self.db.commit()
        self.api.refresh.side_effect=RuntimeError('simulated process interruption')
        with self.assertRaises(RuntimeError):service.token(self.db,1,self.api)
        self.db.rollback();self.db.refresh(row);self.assertTrue(row.refresh_pending)
        with self.assertRaises(PinterestError):service.token(self.db,1,self.api)
        self.api.refresh.assert_called_once()

    def test_rotation_persistence_failure_keeps_claim_and_disconnect_wins(self):
        self.connect();row=self.db.query(Connection).one();row.expires_at=service.utcnow();self.db.commit()
        commit=self.db.commit;calls=0
        def fail_final_commit():
            nonlocal calls
            calls+=1
            if calls==2:raise RuntimeError('simulated database interruption')
            commit()
        with patch.object(self.db,'commit',side_effect=fail_final_commit):
            with self.assertRaises(RuntimeError):service.token(self.db,1,self.api)
        self.db.rollback();self.db.refresh(row);self.assertTrue(row.refresh_pending)
        with self.assertRaises(PinterestError):service.token(self.db,1,self.api)
        self.api.refresh.assert_called_once()
        self.client.post('/auth/pinterest/disconnect',headers={'Origin':ORIGIN})
        self.db.refresh(row);self.assertFalse(row.active);self.assertIsNone(row.encrypted_tokens)

    def test_board_rename_is_escaped_and_environment_change_requires_reconnect(self):
        self.connect();row=self.db.query(Connection).one();row.board_name='<script>bad()</script>';self.db.commit()
        self.assertNotIn('<script>bad()',self.client.get(pinterest.HOME).text)
        self.api.sandbox=False
        self.assertEqual(self.client.get('/api/pinterest/boards').status_code,422)

    def test_invalid_config_and_board_request_fail_without_provider_call(self):
        with patch.object(service,'client',side_effect=PinterestError('not configured')):
            self.assertEqual(self.client.post('/auth/pinterest/login',headers={'Origin':ORIGIN}).status_code,422)
        self.assertEqual(self.db.query(Attempt).count(),0)
        self.assertEqual(self.client.post('/api/pinterest/board',json={'board_id':'../x'},headers={'Origin':ORIGIN}).status_code,422)
        self.api.board.assert_not_called()

    def test_sandbox_board_setup_checks_environment_and_reuses_saved_board(self):
        self.connect();self.api.create_test_board.return_value=BOARD
        self.assertEqual(self.client.post('/api/pinterest/sandbox-board').status_code,403)
        with patch.object(settings,'pinterest_sandbox',False):
            self.assertEqual(self.client.post('/api/pinterest/sandbox-board',headers={'Origin':ORIGIN}).status_code,422)
        self.api.create_test_board.assert_not_called()
        first=self.client.post('/api/pinterest/sandbox-board',headers={'Origin':ORIGIN})
        self.assertEqual(first.status_code,200,first.text);self.assertEqual(first.json()['id'],'123')
        self.assertTrue(self.client.post('/api/pinterest/sandbox-board',headers={'Origin':ORIGIN}).json()['reused'])
        self.api.create_test_board.assert_called_once();self.api.create_pin.assert_not_called()

    def test_sandbox_board_unknown_result_and_save_failure_never_retry_the_write(self):
        from app.services.channels.pinterest import PinterestOutcomeUnknown
        self.connect();self.api.create_test_board.side_effect=PinterestOutcomeUnknown('Load boards before continuing.')
        self.assertEqual(self.client.post('/api/pinterest/sandbox-board',headers={'Origin':ORIGIN}).status_code,422)
        self.api.create_test_board.assert_called_once();self.assertIsNone(self.db.query(Connection).one().board_id)
        self.api.create_test_board.side_effect=None;self.api.create_test_board.return_value=BOARD
        commit=self.db.commit;calls=0
        def fail_save():
            nonlocal calls
            calls+=1
            if calls==2:raise RuntimeError('Interrupted save')
            commit()
        with patch.object(self.db,'commit',side_effect=fail_save):
            response=self.client.post('/api/pinterest/sandbox-board',headers={'Origin':ORIGIN})
        self.assertEqual(response.status_code,422);self.assertIn('Load your boards',response.text)
        self.assertIsNone(self.db.query(Connection).one().board_id);self.assertEqual(self.api.create_test_board.call_count,2)

    def test_test_board_foreign_owner_is_not_selected(self):
        self.connect();self.api.create_test_board.return_value={**BOARD,'owner':{'username':'other'}}
        self.assertEqual(self.client.post('/api/pinterest/sandbox-board',headers={'Origin':ORIGIN}).status_code,422)
        self.assertIsNone(self.db.query(Connection).one().board_id)
