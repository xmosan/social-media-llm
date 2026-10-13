"""Synthetic source/card and mocked provider; never touches live credentials."""
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from app.config import settings
from app.db import get_db
from app.models import Org, User, OrgMember, Post, PinterestConnection as Connection
from app.routes import pinterest, posts
from app.security.auth import get_current_user
from app.services import pinterest_connection as connection, pinterest_publishing as service, post_service
from app.services.channels.pinterest import PinterestError, PinterestOutcomeUnknown
from app.services.media_sequence import seal_manifest, card_digest
from test_security import DatabaseCase

ORIGIN='https://app.sabeelstudio.com'
COPY={'title':'Fixture 1','description':'Synthetic test copy. Fixture 1','alt_text':'Synthetic source card','ai_modified':False,'link':None}


def add_card(db, post_id=1):
    card={'eyebrow':'Fixture 1','headline':'Synthetic source text','arabic_text':'نص تجريبي','supporting_text':''}
    manifest=seal_manifest({'version':1,'format':'feed_4_5','card_digest':card_digest(card),'pages':[
        {'index':0,'url':'https://res.cloudinary.com/fixture/image/upload/v1/card.jpg','width':1080,'height':1350,'quality':{'status':'passed'}}]},1)
    post=Post(id=post_id,org_id=1,status='drafted',source_type='quran',source_reference='Fixture 1',source_text=card['headline'],
        source_metadata={'reference':'Fixture 1','translation_text':card['headline'],'arabic_text':card['arabic_text']},
        card_message=card,caption='Original Instagram caption',post_format='feed_4_5',media_url=manifest['pages'][0]['url'],
        flags={'media_manifest':manifest,'reviewed_manifest':card_digest(manifest)})
    db.add(post);db.commit();return post


class PinterestPublicationTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        for model in (Post,Connection):model.__table__.create(self.engine)
        self.db.add(Org(id=1,name='Fixture'));self.db.flush()
        self.user=User(id=1,email='owner@fixture.test',is_active=True,is_superadmin=True,active_org_id=1)
        self.db.add(self.user);self.db.flush();self.db.add(OrgMember(user_id=1,org_id=1,role='owner'))
        self.row=Connection(org_id=1,user_id=1,username='fixture',active=True,sandbox=True,
            encrypted_tokens=connection.encrypt({'access_token':'synthetic','refresh_token':'synthetic'},1),
            expires_at=connection.utcnow()+timedelta(hours=1),board_id='123',board_name='Fixture board')
        self.db.add(self.row);self.db.commit();self.post=add_card(self.db)
        self.api=Mock(sandbox=True);self.api.account.return_value={'username':'fixture'}
        self.api.board.return_value={'id':'123','privacy':'PUBLIC','owner':{'username':'fixture'}}
        self.api.create_pin.return_value={'id':'456','sandbox':True}
        for patcher in (patch.object(connection,'client',return_value=self.api),patch.object(service,'image_digest',return_value='synthetic-image-hash'),
                        patch.object(settings,'platform_owner_email',self.user.email),patch.object(settings,'pinterest_sandbox',True)):
            patcher.start();self.addCleanup(patcher.stop)
        app=FastAPI();app.include_router(pinterest.router);app.include_router(posts.router)
        app.dependency_overrides[get_db]=lambda:self.db;app.dependency_overrides[get_current_user]=lambda:self.user
        self.client=TestClient(app,base_url=ORIGIN);self.client.cookies.set('access_token','synthetic-cookie');self.addCleanup(self.client.close)

    def review(self, copy=None):
        response=self.client.post('/api/pinterest/posts/1/review',headers={'Origin':ORIGIN},json=copy or COPY)
        self.assertEqual(response.status_code,200,response.text);return response.json()['receipt']

    def send(self, receipt, **changes):
        return self.client.post('/api/pinterest/posts/1/publish',headers={'Origin':ORIGIN},json={**COPY,'receipt':receipt,'reviewed':True,**changes})

    def test_publish_claim_saved_before_send_and_repeat_is_idempotent(self):
        original=(self.post.source_text,deepcopy(self.post.source_metadata),deepcopy(self.post.card_message),self.post.caption,self.post.status)
        def create(*args):
            record=self.db.get(Post,1).flags[service.KEY]
            self.assertEqual(record['status'],'publishing');self.assertEqual(record['payload']['description'],COPY['description'])
            return {'id':'456','sandbox':True}
        self.api.create_pin.side_effect=create
        receipt=self.review();first=self.send(receipt);second=self.send(receipt)
        self.assertEqual(first.status_code,200,first.text);self.assertEqual(first.json()['status'],'published')
        self.assertTrue(second.json()['already_sent']);self.api.create_pin.assert_called_once()
        self.assertEqual(original,(self.post.source_text,self.post.source_metadata,self.post.card_message,self.post.caption,self.post.status))
        self.assertEqual(self.client.get('/api/pinterest/posts/1').json()['pin_id'],'456')

    def test_manual_review_owner_origin_and_workspace_required(self):
        receipt=self.review()
        self.assertEqual(self.send(receipt,reviewed=False).status_code,422)
        self.assertEqual(self.client.post('/api/pinterest/posts/1/publish',json={**COPY,'receipt':receipt,'reviewed':True}).status_code,403)
        self.assertEqual(self.client.get('/api/pinterest/posts/999').status_code,404)
        self.user.is_superadmin=False
        for method,path in [('get','/api/pinterest/posts'),('get','/api/pinterest/posts/1'),('post','/api/pinterest/posts/1/review'),
                            ('post','/api/pinterest/posts/1/publish'),('get','/api/pinterest/posts/1/verify')]:
            self.assertEqual(getattr(self.client,method)(path).status_code,403)
        self.api.create_pin.assert_not_called()

    def test_stale_copy_media_board_and_cross_user_receipts_rejected(self):
        for change in ('copy','media','board','user'):
            with self.subTest(change=change):
                receipt=self.review();extra={}
                with patch.object(service,'image_digest',return_value='changed' if change=='media' else 'synthetic-image-hash'):
                    if change=='copy':extra={'description':'Changed Fixture 1'}
                    if change=='board':self.row.board_id='999';self.db.commit()
                    if change=='user':receipt=service.signer().dumps({'digest':'x','org_id':1,'user_id':999})
                    self.assertEqual(self.send(receipt,**extra).status_code,422)
                self.row.board_id='123';self.db.commit()
        self.api.create_pin.assert_not_called()

    def test_altered_source_unsigned_manifest_and_unreviewed_images_rejected(self):
        original=deepcopy(self.post.flags)
        for change in ('source','manifest','review'):
            with self.subTest(change=change):
                self.post.flags=deepcopy(original);self.post.source_text='changed' if change=='source' else 'Synthetic source text'
                if change=='manifest':self.post.flags={**original,'media_manifest':{**original['media_manifest'],'receipt':'forged'}}
                if change=='review':self.post.flags={**original,'reviewed_manifest':None}
                self.db.commit()
                self.assertEqual(self.client.post('/api/pinterest/posts/1/review',headers={'Origin':ORIGIN},json=COPY).status_code,422)
        self.api.create_pin.assert_not_called()

    def test_sequences_do_not_publish_only_the_cover(self):
        manifest=deepcopy(self.post.flags['media_manifest']);manifest.pop('receipt')
        manifest.update(format='story_9_16',pages=[{**manifest['pages'][0],'height':1920}])
        manifest=seal_manifest(manifest,1)
        self.post.post_format='story_9_16';self.post.flags={'media_manifest':manifest,'reviewed_manifest':card_digest(manifest)};self.db.commit()
        r=self.client.post('/api/pinterest/posts/1/review',headers={'Origin':ORIGIN},json=COPY)
        self.assertEqual(r.status_code,422);self.assertIn('single-card',r.text);self.api.create_pin.assert_not_called()

    def test_unknown_outcome_is_retained_and_never_retried(self):
        self.api.create_pin.side_effect=PinterestOutcomeUnknown('Unknown delivery')
        receipt=self.review();self.assertEqual(self.send(receipt).json()['status'],'unknown')
        self.assertEqual(self.send(receipt).status_code,409);self.api.create_pin.assert_called_once()
        self.assertEqual(self.client.patch('/posts/1',headers={'Origin':ORIGIN},json={'caption':'changed'}).status_code,409)
        self.assertEqual(self.client.delete('/posts/1').status_code,409)

    def test_confirmed_rejection_can_be_reviewed_again_but_not_auto_retried(self):
        self.api.create_pin.side_effect=PinterestError('Provider rejected the Pin')
        self.assertEqual(self.send(self.review()).json()['status'],'failed');self.api.create_pin.assert_called_once()
        self.api.create_pin.side_effect=None
        self.assertEqual(self.send(self.review()).json()['status'],'published');self.assertEqual(self.api.create_pin.call_count,2)

    def test_board_account_change_and_unavailable_media_prevent_write(self):
        receipt=self.review()
        self.api.board.return_value['privacy']='SECRET';self.assertEqual(self.send(receipt).status_code,422)
        self.api.board.return_value['privacy']='PUBLIC';self.api.account.return_value={'username':'other'}
        self.assertEqual(self.send(receipt).status_code,422)
        with patch.object(service,'image_digest',side_effect=ValueError('Image unavailable')):
            self.assertEqual(self.send(receipt).status_code,422)
        self.api.create_pin.assert_not_called()

    def test_commit_failure_before_provider_prevents_write(self):
        receipt=self.review();commit=self.db.commit;calls=0
        def fail_claim():
            nonlocal calls
            calls+=1
            if calls==2:raise RuntimeError('Database interrupted')
            commit()
        with patch.object(self.db,'commit',side_effect=fail_claim):
            with self.assertRaises(RuntimeError):self.send(receipt)
        self.db.rollback();self.api.create_pin.assert_not_called()

    def test_commit_failure_after_provider_keeps_durable_claim(self):
        receipt=self.review();commit=self.db.commit;calls=0
        def fail_final():
            nonlocal calls
            calls+=1
            if calls==3:raise RuntimeError('Database interrupted')
            commit()
        with patch.object(self.db,'commit',side_effect=fail_final):
            self.assertEqual(self.send(receipt).status_code,503)
        self.db.expire_all();self.assertEqual(service.state(self.db.get(Post,1))['status'],'publishing')
        self.assertEqual(self.send(receipt).status_code,409);self.api.create_pin.assert_called_once()

    def test_copy_limits_reference_and_expired_review_fail_before_write(self):
        for copy in ({**COPY,'title':'x'*101},{**COPY,'ai_modified':'yes'},{**COPY,'title':'x','description':'no reference'}):
            self.assertEqual(self.client.post('/api/pinterest/posts/1/review',headers={'Origin':ORIGIN},json=copy).status_code,422)
        receipt=self.review()
        from itsdangerous import TimestampSigner
        with patch.object(TimestampSigner,'get_timestamp',return_value=1):expired=self.review()
        self.assertEqual(self.send(expired).status_code,422);self.assertEqual(self.send('forged').status_code,422)
        self.api.create_pin.assert_not_called()

    def test_persisted_id_readback_compares_copy_without_writing(self):
        self.send(self.review());payload=self.post.flags[service.KEY]['payload']
        self.api.pin.return_value={**payload,'id':'456'}
        self.assertTrue(self.client.get('/api/pinterest/posts/1/verify').json()['verified'])
        self.api.pin.return_value['description']='Changed'
        self.assertFalse(self.client.get('/api/pinterest/posts/1/verify').json()['verified']);self.api.create_pin.assert_called_once()

    def test_post_updates_cannot_forge_pinterest_state(self):
        response=self.client.patch('/posts/1',headers={'Origin':ORIGIN},json={'flags':{service.KEY:{'status':'published','pin_id':'999'}}})
        self.assertEqual(response.status_code,200,response.text);self.assertNotIn(service.KEY,self.db.get(Post,1).flags)

    def test_cross_workspace_lookup_never_exposes_or_publishes_a_post(self):
        with self.assertRaises(HTTPException) as caught:service.review(self.db,1,2,1,COPY)
        self.assertEqual(caught.exception.status_code,404)
        with self.assertRaises(HTTPException) as caught:service.publish(self.db,1,2,1,COPY,self.review(),self.api)
        self.assertEqual(caught.exception.status_code,404);self.api.create_pin.assert_not_called()

    def test_image_bytes_must_be_complete_and_have_expected_dimensions(self):
        from io import BytesIO
        from PIL import Image
        # Exercise the real checker, independently of the per-test provider stub.
        import importlib.util
        path=__import__('pathlib').Path(service.__file__)
        spec=importlib.util.spec_from_file_location('pin_image_check_fixture',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        for size in ((1080,1350),(100,100)):
            data=BytesIO();Image.new('RGB',size,'white').save(data,format='JPEG')
            with patch.object(module,'download_image',return_value=data.getvalue()):
                if size==(1080,1350):self.assertEqual(len(module.image_digest(self.post.media_url)),64)
                else:
                    with self.assertRaises(PinterestError):module.image_digest(self.post.media_url)
            if size==(1080,1350):
                with patch.object(module,'download_image',return_value=data.getvalue()[:-128]):
                    with self.assertRaises(PinterestError):module.image_digest(self.post.media_url)
        with patch.object(module,'download_image',return_value=b'not an image'):
            with self.assertRaisesRegex(PinterestError,'saved image could not be read'):
                module.image_digest(self.post.media_url)
