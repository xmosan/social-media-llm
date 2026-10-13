"""Creator drafts must preserve source/account boundaries and cannot publish."""
from copy import deepcopy
from unittest.mock import Mock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.config import settings
from app.db import get_db
from app.models import Org, User, OrgMember, Post
from app.routes import pinterest_creator, pinterest, posts
from app.security.auth import get_current_user
from app.services import pinterest_drafts as service, pinterest_connection, pinterest_publishing
from test_security import DatabaseCase
from test_pinterest_publication import add_card, COPY, ORIGIN


class PinterestCreatorTests(DatabaseCase):
    def setUp(self):
        super().setUp(); Post.__table__.create(self.engine)
        self.db.add_all([Org(id=1,name='Creator'),Org(id=2,name='Other workspace')]); self.db.flush()
        self.user=User(id=1,email='tester@fixture.test',is_active=True,is_superadmin=False,active_org_id=1)
        self.db.add(self.user); self.db.flush(); self.db.add(OrgMember(user_id=1,org_id=1,role='owner')); self.db.commit()
        self.post=add_card(self.db)
        self.provider=Mock(side_effect=AssertionError('Creator preparation must never contact Pinterest'))
        for p in (patch.object(pinterest_connection,'client',self.provider), patch.object(settings,'platform_owner_email','owner@fixture.test')):
            p.start(); self.addCleanup(p.stop)
        app=FastAPI(); app.include_router(pinterest_creator.router); app.include_router(pinterest.router);app.include_router(posts.router)
        app.dependency_overrides[get_db]=lambda:self.db;app.dependency_overrides[get_current_user]=lambda:self.user
        self.client=TestClient(app,base_url=ORIGIN);self.client.cookies.set('access_token','synthetic');self.addCleanup(self.client.close)

    def get(self):
        r=self.client.get('/api/creator/pinterest/posts/1');self.assertEqual(r.status_code,200,r.text);return r.json()

    def save(self, payload=None):
        data=self.get()
        return self.client.put('/api/creator/pinterest/posts/1',headers={'Origin':ORIGIN},json=payload or {**COPY,'revision':data['revision'],'source_version':data['source_version']})

    def test_regular_tester_can_prepare_save_and_reopen_without_provider_or_instagram_mutation(self):
        original=(self.post.source_text,deepcopy(self.post.source_metadata),deepcopy(self.post.card_message),self.post.caption,self.post.status,self.post.media_url,self.post.ig_account_id)
        r=self.client.get('/app/pinterest');self.assertEqual(r.status_code,200);self.assertIn('no-store',r.headers['cache-control'])
        self.assertIn('Awaiting approval',r.text);self.assertNotIn('/admin/',r.text)
        self.assertEqual(self.save().status_code,200);data=self.get()
        self.assertEqual(data['copy'],COPY);self.assertEqual(data['revision'],1);self.assertFalse(data['publishing_enabled'])
        self.assertEqual(original,(self.post.source_text,self.post.source_metadata,self.post.card_message,self.post.caption,self.post.status,self.post.media_url,self.post.ig_account_id))
        self.assertNotIn('pinterest_publication',self.post.flags);self.provider.assert_not_called()
        self.assertTrue(self.client.get('/api/creator/pinterest/posts').json()['items'][0]['has_draft'])

    def test_preview_preserves_returned_attribution_and_separate_reflection(self):
        self.post.source_metadata={**self.post.source_metadata,'translation_provenance':{'resource_name':'Fixture translator','provider':'Fixture provider'},'translation_footnotes':[{'text':'Exact fixture note'}]}
        self.db.commit();data=self.get()
        self.assertEqual(data['arabic'],self.post.card_message['arabic_text']);self.assertEqual(data['translation'],self.post.source_text)
        self.assertIn('Translation: Fixture translator',data['source_details']);self.assertIn('Exact fixture note',data['source_details'])

    def test_incomplete_copy_is_recoverable_but_never_marked_ready_to_publish(self):
        data=self.get();r=self.save({**data['copy'],'revision':0,'source_version':data['source_version']})
        self.assertEqual(r.status_code,200);self.assertTrue(r.json()['issues']);self.assertIsNone(self.get()['copy']['ai_modified'])

    def test_workspace_and_admin_boundaries(self):
        other=add_card(self.db,2);other.org_id=2;self.db.commit()
        self.assertEqual([p['id'] for p in self.client.get('/api/creator/pinterest/posts').json()['items']],[1])
        self.assertEqual(self.client.get('/api/creator/pinterest/posts/2').status_code,404)
        self.assertEqual(self.client.get('/api/creator/pinterest/posts/2',headers={'X-Org-Id':'2'}).status_code,403)
        self.assertEqual(self.client.get('/admin/connections/pinterest').status_code,403)
        self.assertEqual(self.client.post('/api/pinterest/posts/1/publish',headers={'Origin':ORIGIN},json={**COPY,'receipt':'invalid','reviewed':True}).status_code,403)
        self.assertEqual(self.client.post('/auth/pinterest/login',headers={'Origin':ORIGIN}).status_code,403)
        self.provider.assert_not_called()

    def test_server_release_gate_cannot_be_enabled_by_payload_owner_or_sandbox_setting(self):
        for sandbox in (True,False):
            with patch.object(settings,'pinterest_sandbox',sandbox):
                for suffix in ('connect','posts/1/publish','posts/1/schedule'):
                    r=self.client.post('/api/creator/pinterest/'+suffix,headers={'Origin':ORIGIN},json={'approved':True,'publishing_enabled':True})
                    self.assertEqual(r.status_code,403);self.assertIn('Standard approval',r.text)
        self.user.is_superadmin=True
        with patch.object(settings,'platform_owner_email',self.user.email):
            self.assertEqual(self.client.post('/api/creator/pinterest/posts/1/publish',headers={'Origin':ORIGIN}).status_code,403)
        self.provider.assert_not_called();self.assertNotIn('pinterest_publication',self.post.flags)

    def test_save_rejects_cross_origin_forged_fields_and_bad_limits(self):
        data=self.get();payload={**COPY,'revision':0,'source_version':data['source_version']}
        self.assertEqual(self.client.put('/api/creator/pinterest/posts/1',json=payload).status_code,403)
        for changes in ({'title':'x'*101},{'ai_modified':'false'},{'status':'published'},{'revision':True}):
            r=self.save({**payload,**changes});self.assertEqual(r.status_code,422);self.assertIn('no-store',r.headers['cache-control'])
        self.assertNotIn(service.KEY,self.post.flags)

    def test_lost_response_retry_is_idempotent_and_stale_tabs_do_not_overwrite(self):
        data=self.get();payload={**COPY,'revision':0,'source_version':data['source_version']}
        self.assertEqual(self.save(payload).json()['revision'],1);self.assertEqual(self.save(payload).json()['revision'],1)
        self.assertEqual(self.save({**payload,'title':'Different edit'}).status_code,409)
        self.assertEqual(self.save({**payload,'revision':1,'source_version':'0'*64}).status_code,409)
        self.assertEqual(self.get()['copy'],COPY)

    def test_post_patch_cannot_forge_pin_draft_or_erase_existing_copy(self):
        self.save();r=self.client.patch('/posts/1',headers={'Origin':ORIGIN},json={'caption':'Updated Instagram only','flags':{service.KEY:{'revision':123,'copy':{'title':'forged'}}}})
        self.assertEqual(r.status_code,200,r.text);self.assertEqual(self.get()['copy'],COPY);self.assertEqual(self.post.caption,'Updated Instagram only')

    def test_stale_or_unreviewed_manifest_and_sequences_are_not_presented_as_single_pins(self):
        for fmt in ('story_9_16','carousel_4_5'):
            original=deepcopy(self.post.flags);self.post.flags={**original,'media_manifest':{**original['media_manifest'],'format':fmt}};self.db.commit()
            self.assertEqual(self.client.get('/api/creator/pinterest/posts/1').status_code,422)
            self.post.flags=original;self.db.commit()
        self.post.flags={**self.post.flags,'reviewed_manifest':None};self.db.commit()
        self.assertEqual(self.client.get('/api/creator/pinterest/posts/1').status_code,422)

    def test_submitted_copy_is_read_only(self):
        self.post.flags={**self.post.flags,'pinterest_publication':{'status':'unknown','payload':{**COPY,'ai_disclosures':{'values':[]}}}};self.db.commit()
        self.assertTrue(self.get()['locked']);self.assertEqual(self.save().status_code,409)
        self.assertNotIn(service.KEY,self.post.flags)

    def test_revoked_workspace_and_signed_out_user_cannot_read(self):
        from datetime import datetime,timezone
        self.db.get(Org,1).tester_revoked_at=datetime.now(timezone.utc);self.db.commit()
        self.assertEqual(self.client.get('/app/pinterest').status_code,403)
        self.user=None
        self.assertEqual(self.client.get('/api/creator/pinterest/posts').status_code,401)

    def test_pagination_never_mixes_workspaces(self):
        for id in range(2,33):add_card(self.db,id)
        first=self.client.get('/api/creator/pinterest/posts').json();self.assertEqual(len(first['items']),30)
        second=self.client.get('/api/creator/pinterest/posts?before='+str(first['next_before'])).json()
        self.assertEqual([i['id'] for i in second['items']],[2,1]);self.assertIsNone(second['next_before'])
