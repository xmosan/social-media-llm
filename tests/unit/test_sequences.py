"""Exact-source pagination, persisted manifests and non-atomic Story delivery."""
import io
import json
import tempfile
import unittest
import zipfile
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from test_security import DatabaseCase
from test_image_provider import load_real_service
from app.config import settings
from app.db import get_db
from app.models import Org, IGAccount, Post
from app.routes import studio, posts
from app.security.auth import get_current_user
from app.security.rbac import get_current_org_id
from app.services import card_typography as type_service, media_sequence as media, publisher, post_service

CDN = 'https://res.cloudinary.com/fixture/image/upload/page'
CARD = {'eyebrow':'Synthetic reference', 'headline':'A complete synthetic source.', 'arabic_text':'', 'supporting_text':''}


def manifest(card=None, fmt='story_9_16', count=2, owner=1):
    card = card or CARD
    pages = [{'index':i,'url':f'{CDN}{i}.jpg','label':f'Page {i+1}', 'slices':[],
              'width':1080,'height':1920 if fmt=='story_9_16' else 1350,'quality':{'status':'passed'}} for i in range(count)]
    # Synthetic source split at exact offsets, with one complete range per page.
    text = card['headline']; cut=len(text)//count
    for i,p in enumerate(pages):
        p['slices']=[{'role':'source_translation','start':i*cut,'end':len(text) if i==count-1 else (i+1)*cut}]
    return media.seal_manifest({'version':1,'format':fmt,'card_digest':media.card_digest(card),'pages':pages},owner)


class SequenceLayoutTests(unittest.TestCase):
    def test_honorific_keeps_translation_font_consistent_across_pages(self):
        record=json.loads((Path(__file__).resolve().parents[1]/'fixtures/hadith_bukhari_1.json').read_text())
        segments=[{'role':role,'text':record[key]} for role,key in [('reference','reference'),('source_translation','translation_text'),('source_arabic','arabic_text')]]
        pages=type_service.plan_sequence(segments,family='quiet_photography')
        fonts=[]
        for page in pages:
            _,blocks=type_service.layout_card(page['segments'],family='quiet_photography')
            fonts.extend(str(b['font'].path) for b in blocks if b['role']=='source_translation')
        self.assertGreater(len(fonts),1)
        self.assertEqual(len(set(fonts)),1)
        self.assertTrue(fonts[0].endswith('Amiri-Regular.ttf'))

    def test_actual_review_records_keep_complete_exact_slices_and_story_safe_areas(self):
        for fixture in ('quran_94_6','quran_21_37','hadith_bukhari_1'):
            record=json.loads((Path(__file__).resolve().parents[1]/'fixtures'/f'{fixture}.json').read_text())
            segments=[{'role':role,'text':record[key]} for role,key in [('reference','reference'),('source_translation','translation_text'),('source_arabic','arabic_text')]]
            for fmt in ('feed_4_5','story_9_16'):
                for family in type_service.DESIGN_FAMILIES:
                    for order in type_service.FEED_LAYOUTS:
                        with self.subTest(fixture=fixture,fmt=fmt,family=family,order=order):
                            if family == 'emerald_forest' and fixture == 'hadith_bukhari_1':
                                with self.assertRaisesRegex(type_service.CardTypographyError, 'Quiet Nature needs more open space'):
                                    type_service.plan_sequence(segments,family=family,layout=order,post_format=fmt)
                                continue
                            pages=type_service.plan_sequence(segments,family=family,layout=order,post_format=fmt)
                            self.assertLessEqual(len(pages),10)
                            for segment in segments:
                                if segment['role']=='reference': continue
                                restored=''.join(s['text'] for p in pages for s in p['segments'] if s['role']==segment['role'])
                                self.assertEqual(restored,segment['text'])
                            for page in pages:
                                size,blocks=type_service.layout_card(page['segments'],family=family,layout=order,post_format=fmt)
                                self.assertEqual(size,(1080,1920 if fmt=='story_9_16' else 1350))
                                self.assertTrue(any(s['role']=='reference' and s['text']==record['reference'] for s in page['segments']))
                                if fmt=='story_9_16':
                                    self.assertTrue(all(b['bounds'][1]>=250 and b['bounds'][3]<=1610 for b in blocks))
                            if fixture=='hadith_bukhari_1': self.assertGreater(len(pages),1)

    def test_whitespace_marks_and_punctuation_are_preserved_at_page_boundaries(self):
        text=('A synthetic sentence.  Next paragraph.\n\nAnother sentence with marks (ﷺ).\n' * 15)
        pages=type_service.plan_sequence([{'role':'reference','text':'Fixture'}, {'role':'source_translation','text':text}])
        parts=[s for page in pages for s in page['slices'] if s['role']=='source_translation']
        self.assertEqual(''.join(text[p['start']:p['end']] for p in parts),text)
        self.assertEqual(''.join(s['text'] for page in pages for s in page['segments'] if s['role']=='source_translation'),text)

    def test_long_sequence_reuses_one_photograph_and_rejects_over_limit_before_generation(self):
        renderer=load_real_service('image_renderer')
        with patch.dict('sys.modules',{'app.services.image_renderer':renderer}):
            image_card=load_real_service('image_card')
        record=json.loads((Path(__file__).resolve().parents[1]/'fixtures/hadith_bukhari_1.json').read_text())
        card={'headline':record['translation_text'],'arabic_text':record['arabic_text'],'eyebrow':record['reference']}
        with tempfile.TemporaryDirectory() as directory, patch.object(settings,'uploads_dir',directory), patch.object(renderer,'generate_background',return_value=Image.new('RGB',(300,300),(180,175,160))) as generate, patch('app.config.build_public_media_url',side_effect=lambda filename,local_path:f'https://res.cloudinary.com/fixture/image/upload/{filename}'):
            metadata={}; sink=Mock()
            image_card.generate_quote_card(card_message=card,style='quiet_photography',allow_sequence=True,render_metadata=metadata,background_sink=sink)
            generate.assert_called_once();sink.assert_called_once()
            m=media.seal_manifest(metadata['media_manifest'],1)
            media.validate_manifest(m,card,1)
            self.assertGreater(len(m['pages']),1)
            self.assertEqual(len(set(p['url'] for p in m['pages'])),len(m['pages']))
            generate.reset_mock()
            with self.assertRaises(ValueError):
                image_card.generate_quote_card(card_message={'headline':'Long source. '*3000},style='quiet_photography',allow_sequence=True,render_metadata={})
            generate.assert_not_called()

    def test_new_hadith_cards_use_full_translation_while_saved_excerpts_remain_valid(self):
        from app.services.quote_message_service import build_hadith_quote_message
        from app.services.source_grounding import validate_source_card
        record={'reference':'Synthetic hadith fixture','translation_text':'Complete returned synthetic translation.', 'card_text':'Complete returned', 'was_excerpted':True,'arabic_text':'نص تجريبي','grade':None}
        with patch('app.services.llm.generate_card_framing_from_source',return_value={'supporting_text':'Separate reflection'}):
            card=build_hadith_quote_message(record, "calm", "wisdom")
        self.assertEqual(card['headline'],record['translation_text']);self.assertFalse(card['was_excerpted'])
        validate_source_card(card,record,'hadith')
        validate_source_card({'headline':record['card_text'],'eyebrow':record['reference'],'arabic_text':record['arabic_text']},record,'hadith')


class SequenceLifecycleTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        for model in (IGAccount,Post):model.__table__.create(self.engine)
        self.db.add(Org(id=1,name='Fixture'));self.db.add(IGAccount(id=1,org_id=1,name='Fixture',ig_user_id='123',access_token='fake',active=True));self.db.commit()
        self.app=FastAPI();self.app.include_router(studio.router);self.app.include_router(posts.router)
        self.app.dependency_overrides[get_db]=lambda:self.db
        self.app.dependency_overrides[get_current_org_id]=lambda:1
        self.app.dependency_overrides[get_current_user]=lambda:None
        self.client=TestClient(self.app);self.addCleanup(self.client.close)
    def save(self,fmt='story_9_16',count=2):
        m=manifest(fmt=fmt,count=count)
        payload={'ig_account_id':1,'draft_key':'11111111-1111-4111-8111-111111111111','source_type':'manual','card_message':CARD,'caption_message':{'caption':'Separate caption'},'visual_design':{'family':'editorial','media_manifest':m},'media_url':m['pages'][0]['url'],'post_format':fmt,'reviewed':True}
        result=self.client.post('/api/studio/create-post',json=payload)
        self.assertEqual(result.status_code,200,result.text)
        return result.json()['id'],payload
    def test_draft_recovery_is_idempotent_and_ordered_export_contains_full_source(self):
        id,payload=self.save(); again=self.client.post('/api/studio/create-post',json=payload)
        self.assertEqual(again.json()['id'],id);self.assertEqual(self.db.query(Post).count(),1)
        reopened=self.client.get(f'/api/studio/post/{id}').json()
        self.assertEqual(reopened['card_message'],CARD)
        self.assertEqual(reopened['flags']['media_manifest'],payload['visual_design']['media_manifest'])
        with patch.object(media,'download_image',side_effect=[b'first',b'second']):
            res=self.client.get(f'/posts/{id}/export')
        self.assertEqual(res.status_code,200)
        with zipfile.ZipFile(io.BytesIO(res.content)) as z:
            self.assertEqual(z.read('01.jpg'),b'first');self.assertEqual(z.read('02.jpg'),b'second')
            self.assertEqual(json.loads(z.read('source.json'))['card_message'],CARD)
            self.assertEqual(z.read('caption.txt'),b'Separate caption')
        payload.update(post_id=id,caption_message={'caption':'Edited social copy'})
        self.assertEqual(self.client.post('/api/studio/create-post',json=payload).status_code,200)
        self.assertEqual(self.db.get(Post,id).caption,'Edited social copy')
        with patch.object(media,'download_image',side_effect=ValueError('Unavailable')):
            self.assertEqual(self.client.get(f'/posts/{id}/export').status_code,422)
    def test_manifest_tampering_wrong_owner_incomplete_source_and_stale_edits_fail(self):
        m=manifest();media.validate_manifest(m,CARD,1)
        for change in ('owner','page','text','omitted'):
            bad=deepcopy(m);card=deepcopy(CARD);owner=1
            if change=='owner':owner=2
            if change=='page':bad['pages'].reverse()
            if change=='text':card['headline']='Different'
            if change=='omitted':
                bad['pages'][0]['slices'][0]['start']=2;bad=media.seal_manifest(bad,1)
            with self.assertRaises(ValueError):media.validate_manifest(bad,card,owner)
        id,payload=self.save();post=self.db.get(Post,id)
        self.assertEqual(self.client.patch(f'/posts/{id}',json={'post_format':'feed_4_5'}).status_code,422)
        self.client.patch(f'/posts/{id}',json={'flags':{}})
        self.assertIsNotNone(post.flags.get('media_manifest'))
        post.flags={**post.flags,'reviewed_manifest':None};self.db.commit()
        with patch.object(publisher,'publish_to_instagram') as send:
            self.assertEqual(self.client.post(f'/posts/{id}/publish').status_code,422);send.assert_not_called()

    def test_render_measurements_survive_browser_json_number_normalization(self):
        m=manifest()
        m['pages'][0]['quality']['blocks']=[{'font_at_390px':13.0,'minimum_contrast':7.62}]
        m=media.seal_manifest(m,1)
        # Actual Node JSON.parse/stringify reproduction: 13.0 returns as 13.
        browser_copy=json.loads(json.dumps(m),parse_float=lambda s: int(float(s)) if float(s).is_integer() else float(s))
        self.assertIs(type(browser_copy['pages'][0]['quality']['blocks'][0]['font_at_390px']),int)
        media.validate_manifest(browser_copy,CARD,1)
        browser_copy['pages'][0]['quality']['blocks'][0]['font_at_390px']=12
        with self.assertRaises(ValueError):media.validate_manifest(browser_copy,CARD,1)
    def test_carousel_and_legacy_single_share_same_publish_claim(self):
        id,_=self.save('carousel_4_5')
        def send(**kw):
            self.assertEqual(kw['media_urls'],[f'{CDN}0.jpg',f'{CDN}1.jpg'])
            self.assertEqual(post_service.publish_post(self.db,id,1).status_code,409)
            kw['on_container_created']('100')
            return {'ok':True,'remote_id':'101','creation_id':'100'}
        with patch.object(publisher,'publish_to_instagram',side_effect=send) as publish:
            self.assertTrue(post_service.publish_post(self.db,id,1).ok)
            self.assertTrue(post_service.publish_post(self.db,id,1).ok);publish.assert_called_once()
    def test_partial_story_then_unknown_frame_reconciles_and_resumes_without_duplicates(self):
        id,_=self.save(count=3)
        calls=[]
        def send(**kw):
            i=int(kw['media_url'].split('page')[1][0]);calls.append(i);kw['on_container_created'](str(100+i))
            return {'ok':True,'remote_id':str(200+i)} if i==0 else {'ok':False,'outcome':'unknown','error':'Uncertain'}
        with patch.object(publisher,'validate_story_account'),patch.object(publisher,'verify_sequence_images'),patch.object(publisher,'publish_to_instagram',side_effect=send):
            self.assertFalse(post_service.publish_post(self.db,id,1).ok)
        self.assertEqual(calls,[0,1]);self.assertEqual(self.db.get(Post,id).status,'publish_unknown')
        self.assertEqual(self.client.patch(f'/posts/{id}',json={'caption':'changed'}).status_code,409)
        with patch.object(publisher,'get_container_status',return_value='PUBLISHED') as status:
            self.assertTrue(post_service.reconcile_publication(self.db,id,1).ok)
            status.assert_called_once_with('101','fake')
        self.assertEqual(self.db.get(Post,id).status,'publish_partial')
        self.assertEqual(self.client.patch(f'/posts/{id}',json={'caption':'changed'}).status_code,409)
        with patch.object(publisher,'validate_story_account'),patch.object(publisher,'verify_sequence_images'),patch.object(publisher,'publish_to_instagram',return_value={'ok':True,'remote_id':'202'}) as publish:
            self.assertTrue(post_service.publish_post(self.db,id,1).ok)
            publish.assert_called_once();self.assertEqual(publish.call_args.kwargs['media_url'],f'{CDN}2.jpg')
            self.assertTrue(post_service.publish_post(self.db,id,1).ok);publish.assert_called_once()
        self.assertEqual([f['state'] for f in self.db.get(Post,id).flags['publication']['frames']],['published']*3)
    def test_story_connection_failure_does_not_claim_or_schedule(self):
        id,_=self.save()
        with patch.object(publisher,'validate_story_account',side_effect=ValueError('Reconnect Instagram')),patch.object(publisher,'publish_story_sequence') as send:
            self.assertEqual(post_service.publish_post(self.db,id,1).status_code,422)
            with self.assertRaises(HTTPException):post_service.prepare_scheduled_post(self.db,self.db.get(Post,id))
            send.assert_not_called()
        self.assertEqual(self.db.get(Post,id).status,'drafted')
    def test_lost_container_commit_never_sends_publication(self):
        with patch.object(publisher,'verify_sequence_images'),patch.object(publisher,'verify_single_image'),patch.object(publisher,'create_container',return_value='123'),patch.object(publisher,'publish_container') as publish:
            with self.assertRaises(RuntimeError):publisher.publish_story_sequence(media_urls=[f'{CDN}0.jpg'],ig_user_id='123',access_token='fake',frames=[{'index':0,'state':'pending'}],on_progress=Mock(side_effect=RuntimeError('DB unavailable')))
            publish.assert_not_called()


class SequenceProtocolTests(unittest.TestCase):
    def test_story_identity_uses_supported_facebook_fields_and_eligibility_failure_never_publishes(self):
        with patch('requests.get',return_value=Mock(status_code=200,json=Mock(return_value={'id':'123'}))) as get:
            publisher.validate_story_account('123','fake')
            self.assertEqual(get.call_args.kwargs['params'],{'fields':'id'})
        with patch('requests.get',return_value=Mock(status_code=200,json=Mock(return_value={'id':'999'}))),self.assertRaises(ValueError):
            publisher.validate_story_account('123','fake')
        with patch.object(publisher,'verify_single_image'),patch.object(publisher,'create_container',return_value=None),patch.object(publisher,'publish_container') as send:
            result=publisher.publish_to_instagram(caption='',media_url=f'{CDN}0.jpg',ig_user_id='123',access_token='fake',story=True)
            self.assertIn('Business account',result['error']);send.assert_not_called()

    def test_carousel_child_order_parent_caption_and_single_publish(self):
        responses=[Mock(status_code=200,json=Mock(return_value={'id':str(id)})) for id in (11,12,13,14)]
        with patch.object(publisher,'verify_sequence_images'),patch.object(publisher,'verify_single_image'),patch.object(publisher,'get_container_status',return_value='FINISHED'),patch.object(publisher.requests,'post',side_effect=responses) as request:
            result=publisher.publish_to_instagram(caption='Reviewed caption',media_url=f'{CDN}0.jpg',media_urls=[f'{CDN}0.jpg',f'{CDN}1.jpg'],ig_user_id='123',access_token='fake',on_container_created=Mock())
        self.assertTrue(result['ok']);self.assertEqual(len(request.call_args_list),4)
        bodies=[call.kwargs['data'] for call in request.call_args_list]
        self.assertEqual(bodies[0]['is_carousel_item'],'true');self.assertNotIn('caption',bodies[0])
        self.assertEqual(bodies[2]['media_type'],'CAROUSEL');self.assertEqual(bodies[2]['children'],'11,12')
        self.assertEqual(bodies[3]['creation_id'],'13')
    def test_story_omits_caption_and_incomplete_carousel_never_publishes(self):
        with patch.object(publisher,'verify_single_image'),patch.object(publisher,'create_container',return_value='1') as create,patch.object(publisher,'publish_container',return_value={'ok':True}) as send:
            publisher.publish_to_instagram(caption='Private social notes',media_url=f'{CDN}0.jpg',ig_user_id='1',access_token='fake',story=True)
            self.assertEqual(create.call_args.args[2],{'image_url':f'{CDN}0.jpg','media_type':'STORIES'})
        with patch.object(publisher,'verify_sequence_images'),patch.object(publisher,'verify_single_image'),patch.object(publisher,'create_container',return_value='1'),patch.object(publisher,'wait_until_ready',return_value=False),patch.object(publisher,'publish_container') as send:
            result=publisher.publish_to_instagram(caption='Caption',media_url=f'{CDN}0.jpg',media_urls=[f'{CDN}0.jpg',f'{CDN}1.jpg'],ig_user_id='1',access_token='fake')
            self.assertFalse(result['ok']);send.assert_not_called()
    def test_all_images_checked_before_any_publish_and_cdn_redirects_rejected(self):
        with patch.object(publisher,'verify_sequence_images',side_effect=ValueError('Missing second frame')),patch.object(publisher,'publish_to_instagram') as send:
            result=publisher.publish_story_sequence(media_urls=[f'{CDN}0.jpg',f'{CDN}1.jpg'],ig_user_id='123',access_token='fake',frames=[{'state':'pending'}]*2,on_progress=Mock())
            self.assertFalse(result['ok']);send.assert_not_called()
        response=Mock(status_code=302);response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        with patch('requests.get',return_value=response) as get,self.assertRaises(ValueError):media.download_image(f'{CDN}0.jpg')
        self.assertFalse(get.call_args.kwargs['allow_redirects'])
