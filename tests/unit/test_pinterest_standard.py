"""Standard-access creator flow: isolated fixtures, no live provider or data."""
from copy import deepcopy
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware
from app.config import settings
from app.db import get_db
from app.models import Org, User, OrgMember, Post, PinterestConnection as Connection, PinterestConnectionAttempt as Attempt
from app.routes import pinterest_creator, pinterest
from app.security.auth import get_current_user
from app.services import pinterest_connection as connection, pinterest_drafts as drafts, pinterest_publishing as publishing
from test_security import DatabaseCase
from test_pinterest_publication import add_card, COPY, ORIGIN


class PinterestStandardTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        for model in (Post, Connection, Attempt): model.__table__.create(self.engine)
        self.db.add_all([Org(id=1,name='Creator'),Org(id=2,name='Other')]); self.db.flush()
        self.user=User(id=1,email='creator@fixture.test',is_active=True,is_superadmin=False,active_org_id=1)
        self.db.add(self.user); self.db.flush(); self.db.add(OrgMember(user_id=1,org_id=1,role='owner')); self.db.commit()
        self.post=add_card(self.db)
        self.tokens={'access_token':'fixture-access','refresh_token':'fixture-refresh','expires_in':3600,'scope':'boards:read boards:write pins:read pins:write user_accounts:read'}
        self.row=Connection(org_id=1,user_id=1,username='fixture',active=True,sandbox=False,
            encrypted_tokens=connection.encrypt(self.tokens,1),expires_at=connection.utcnow()+timedelta(hours=1),board_id='123',board_name='Reminders')
        self.db.add(self.row); self.db.commit()
        self.api=Mock(sandbox=False)
        self.api.authorization_url.side_effect=lambda state:'https://www.pinterest.com/oauth/?state='+state
        self.api.exchange_code.return_value=self.tokens; self.api.account.return_value={'username':'fixture'}
        self.api.board.return_value={'id':'123','name':'Reminders','privacy':'PUBLIC','owner':{'username':'fixture'}}
        self.api.boards.return_value={'items':[self.api.board.return_value],'bookmark':None}
        self.api.create_pin.return_value={'id':'456','sandbox':False}
        for item in (patch.object(connection,'client',return_value=self.api),patch.object(settings,'pinterest_sandbox',False),
                     patch.object(settings,'pinterest_creator_enabled',True),patch.object(publishing,'image_digest',return_value='fixture-image'),
                     patch.object(pinterest_creator,'check_auth_attempt')):
            item.start(); self.addCleanup(item.stop)
        app=FastAPI(); app.include_router(pinterest_creator.router); app.include_router(pinterest.router)
        app.add_middleware(SessionMiddleware,secret_key=settings.secret_key,https_only=True,same_site='lax')
        app.dependency_overrides[get_db]=lambda:self.db; app.dependency_overrides[get_current_user]=lambda:self.user
        self.client=TestClient(app,base_url=ORIGIN,follow_redirects=False); self.client.cookies.set('access_token','fixture');self.addCleanup(self.client.close)

    def request(self,path,payload=None):
        return self.client.post('/api/creator/pinterest/'+path,headers={'Origin':ORIGIN},json=payload)

    def save(self):
        p=self.client.get('/api/creator/pinterest/posts/1').json()
        r=self.client.put('/api/creator/pinterest/posts/1',headers={'Origin':ORIGIN},json={**COPY,'revision':p['revision'],'source_version':p['source_version']})
        self.assertEqual(r.status_code,200,r.text)
        self.version={k:r.json()[k] for k in ('revision','source_version')}
        return r.json()

    def review(self):
        self.save(); r=self.request('posts/1/review',self.version)
        self.assertEqual(r.status_code,200,r.text)
        return {**self.version,'receipt':r.json()['receipt'],'reviewed':True}

    def start(self):
        r=self.request('connect');self.assertEqual(r.status_code,303,r.text)
        return parse_qs(urlsplit(r.headers['location']).query)['state'][0]

    def test_creator_connects_without_owner_access_and_cancel_keeps_connection(self):
        page=self.client.get('/app/pinterest');self.assertEqual(page.headers['referrer-policy'],'same-origin')
        state=self.start()
        r=self.client.get('/auth/pinterest/callback',params={'state':state,'code':'fixture'})
        self.assertEqual(r.headers['location'],'/app/pinterest?result=connected')
        self.db.refresh(self.row);self.assertFalse(self.row.sandbox);self.assertIsNone(self.row.board_id)
        self.assertEqual(connection.decrypt(self.row),self.tokens);self.assertNotIn('fixture-access',self.row.encrypted_tokens)
        self.assertEqual(self.client.get('/auth/pinterest/callback',params={'state':state,'code':'fixture'}).status_code,403)
        self.api.exchange_code.assert_called_once()
        state=self.start();r=self.client.get('/auth/pinterest/callback',params={'state':state,'error':'denied'})
        self.assertEqual(r.headers['location'],'/app/pinterest?result=cancelled');self.assertTrue(self.row.active)
        self.assertEqual(self.client.get('/admin/connections/pinterest').status_code,403)

    def test_callback_state_workspace_and_release_switch_are_bound(self):
        state=self.start()
        self.assertEqual(self.client.get('/auth/pinterest/callback',params={'state':'x'*43,'code':'fixture'}).status_code,400)
        with patch.object(settings,'pinterest_creator_enabled',False):
            self.assertEqual(self.client.get('/auth/pinterest/callback',params={'state':state,'code':'fixture'}).status_code,403)
        self.db.add(OrgMember(user_id=1,org_id=2,role='owner'));self.user.active_org_id=2;self.db.commit()
        self.assertEqual(self.client.get('/auth/pinterest/callback',params={'state':state,'code':'fixture'}).status_code,400)
        self.api.exchange_code.assert_not_called()

    def test_sandbox_or_disabled_switch_never_opens_creator_writes(self):
        for name,value in [('pinterest_sandbox',True),('pinterest_creator_enabled',False)]:
            with patch.object(settings,name,value):
                for path in ['connect','board','posts/1/review','posts/1/publish']:
                    self.assertEqual(self.request(path,{}).status_code,403)
                self.assertFalse(self.client.get('/api/creator/pinterest/connection').json()['enabled'])
        self.api.create_pin.assert_not_called()
        self.assertEqual(self.request('posts/1/schedule',{}).status_code,403)

    def test_board_choice_checks_ownership_and_cross_origin(self):
        self.assertEqual(self.client.post('/api/creator/pinterest/board',json={'board_id':'123'}).status_code,403)
        self.assertEqual(self.request('board',{'board_id':'123'}).status_code,200)
        self.api.board.return_value={**self.api.board.return_value,'privacy':'SECRET'}
        self.assertEqual(self.request('board',{'board_id':'123'}).status_code,422)
        self.assertEqual(self.client.get('/api/creator/pinterest/connection',headers={'X-Org-Id':'2'}).status_code,403)
        self.api.create_pin.assert_not_called()

    def test_saved_reviewed_pin_publishes_once_and_preserves_canonical_layers(self):
        original=(self.post.source_text,deepcopy(self.post.source_metadata),deepcopy(self.post.card_message),self.post.caption,self.post.media_url,self.post.status)
        payload=self.review()
        r=self.request('posts/1/publish',payload);self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['status'],'published')
        self.assertTrue(self.request('posts/1/publish',payload).json()['already_sent']);self.api.create_pin.assert_called_once()
        self.assertEqual(original,(self.post.source_text,self.post.source_metadata,self.post.card_message,self.post.caption,self.post.media_url,self.post.status))
        data=self.client.get('/api/creator/pinterest/posts/1').json();self.assertTrue(data['locked']);self.assertEqual(data['copy'],COPY)
        self.api.pin.return_value={'id':'456','board_id':'123',**COPY}
        self.assertTrue(self.client.get('/api/creator/pinterest/posts/1/verify').json()['verified'])

    def test_no_review_missing_copy_stale_revision_and_mutated_destination_do_not_publish(self):
        payload=self.review()
        self.assertEqual(self.request('posts/1/publish',{**payload,'reviewed':False}).status_code,422)
        self.assertEqual(self.request('posts/1/publish',{**payload,'revision':8}).status_code,409)
        self.assertEqual(self.request('posts/1/publish',{**payload,'title':'forged'}).status_code,422)
        self.row.board_id='999';self.db.commit()
        self.assertEqual(self.request('posts/1/publish',payload).status_code,422)
        self.api.create_pin.assert_not_called()

    def test_draft_changed_during_token_refresh_is_rechecked_under_publish_lock(self):
        payload=self.review();original=connection.token
        def changed(*args):
            result=original(*args)
            record=self.post.flags[drafts.KEY]
            self.post.flags={**self.post.flags,drafts.KEY:{**record,'revision':record['revision']+1}}
            self.db.commit();return result
        with patch.object(connection,'token',side_effect=changed):
            self.assertEqual(self.request('posts/1/publish',payload).status_code,409)
        self.api.create_pin.assert_not_called()

    def test_uncertain_delivery_retained_and_not_replayed(self):
        from app.services.channels.pinterest import PinterestOutcomeUnknown
        self.api.create_pin.side_effect=PinterestOutcomeUnknown('Delivery uncertain')
        payload=self.review();self.assertEqual(self.request('posts/1/publish',payload).json()['status'],'unknown')
        self.assertEqual(self.request('posts/1/publish',payload).status_code,409);self.api.create_pin.assert_called_once()
        self.assertEqual(self.client.get('/api/creator/pinterest/posts/1/status').json()['status'],'unknown')

    def test_incomplete_draft_can_be_saved_but_not_reviewed(self):
        data=self.save();payload={**data['copy'],'ai_modified':None,**self.version}
        r=self.client.put('/api/creator/pinterest/posts/1',headers={'Origin':ORIGIN},json=payload)
        self.assertEqual(r.status_code,200)
        self.assertEqual(self.request('posts/1/review',{'revision':2,'source_version':data['source_version']}).status_code,422)

    def test_disconnect_removes_credentials_but_keeps_draft_even_during_pause(self):
        self.save()
        with patch.object(settings,'pinterest_creator_enabled',False):
            self.assertEqual(self.request('disconnect').status_code,200)
        self.db.refresh(self.row);self.assertFalse(self.row.active);self.assertIsNone(self.row.encrypted_tokens)
        self.assertEqual(self.post.flags[drafts.KEY]['copy'],COPY)
