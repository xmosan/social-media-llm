"""Workspace isolation, draft snapshots, exact display excerpts and typography."""
import io
import json
import tempfile
import unittest
import zipfile
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from test_security import DatabaseCase
from test_image_provider import load_real_service
from app.config import settings
from app.db import get_db
from app.models import Org, User, IGAccount, Post
from app.routes import studio
from app.security.auth import require_user, get_current_user
from app.security.rbac import get_current_org_id
from app.services.brand_kit import normalize_brand, workspace_brand, editorial_context, PALETTES, composition_for
from app.services.source_display import arabic_display_options, display_range, narration_boundary
from app.services.source_grounding import validate_source_card
from app.services import media_sequence as media, quote_message_service as messages
from app.services.card_typography import layout_card, plan_sequence, paint_card_text, CardTypographyError

FIXTURE=json.loads((Path(__file__).resolve().parents[1]/'fixtures/hadith_bukhari_1.json').read_text())
CARD={'eyebrow':FIXTURE['reference'],'headline':FIXTURE['translation_text'],'arabic_text':FIXTURE['arabic_text'],'source_complete':True}
BRAND=normalize_brand({'palette':'night','typography':'classic','signature':'@fixture','series_name':'Quiet reminders'})

class BrandRoutesTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        for model in (IGAccount,Post):model.__table__.create(self.engine)
        self.db.add_all([Org(id=1,name='A'),Org(id=2,name='B'),IGAccount(id=1,org_id=1,name='A',ig_user_id='123',access_token='fake',active=True)])
        self.db.commit()
        app=FastAPI();app.include_router(studio.router)
        app.dependency_overrides[get_db]=lambda:self.db
        app.dependency_overrides[get_current_org_id]=lambda:1
        app.dependency_overrides[require_user]=lambda:User(id=1)
        app.dependency_overrides[get_current_user]=lambda:User(id=1)
        self.client=TestClient(app);self.addCleanup(self.client.close)
    def test_visual_preferences_persist_without_changing_legacy_snapshots(self):
        self.assertEqual(normalize_brand({**BRAND, 'visual_identity':'  '}), BRAND)
        identity='Coastal scenes, muted blue, night lighting. No buildings.'
        kit=normalize_brand({**BRAND,'visual_identity':identity})
        revision=self.client.get('/api/studio/brand-kit').json()['revision']
        response=self.client.put('/api/studio/brand-kit',json={'brand_kit':kit,'revision':revision})
        self.assertEqual(response.status_code,200,response.text)
        self.db.expire_all()
        self.assertEqual(workspace_brand(self.db,1)['visual_identity'],identity)
        self.assertNotIn('visual_identity',workspace_brand(self.db,2))
        for value in [None, 12, 'x'*401, 'invisible\u202econtrol']:
            with self.assertRaises(ValueError): normalize_brand({'visual_identity':value})

    def test_recent_visual_history_is_tenant_scoped_and_includes_studio_and_automations(self):
        from app.services.rotation_engine import workspace_visual_history
        from datetime import datetime, timezone
        for org, flags, meta in [(1, {'visual_design':{'prompt_signature':'studio-a'}}, {}),
                                  (1, {}, {'visual_generation':{'prompt_signature':'auto-a'}}),
                                  (2, {'visual_design':{'prompt_signature':'other-b'}}, {})]:
            self.db.add(Post(org_id=org,ig_account_id=1,status='drafted',flags=flags,source_metadata=meta,created_at=datetime.now(timezone.utc)))
        self.db.commit()
        self.assertEqual(set(workspace_visual_history(self.db,1)), {'studio-a','auto-a'})

    def test_persistent_workspace_brand_rejects_stale_save_and_does_not_cross_tenants(self):
        original=self.client.get('/api/studio/brand-kit').json()
        result=self.client.put('/api/studio/brand-kit',json={'brand_kit':BRAND,'revision':original['revision']})
        self.assertEqual(result.status_code,200,result.text)
        self.db.expire_all()
        self.assertEqual(workspace_brand(self.db,1),BRAND)
        self.assertEqual(workspace_brand(self.db,2),normalize_brand())
        self.assertEqual(self.client.put('/api/studio/brand-kit',json={'brand_kit':normalize_brand(),'revision':original['revision']}).status_code,409)
        self.assertEqual(self.client.get('/api/studio/brand-kit').json()['brand_kit'],BRAND)
    def test_caption_only_edit_reopen_and_export_retain_signed_brand_snapshot(self):
        card={'headline':'Synthetic source','eyebrow':'Fixture'}
        page={'index':0,'url':'https://res.cloudinary.com/fixture/image/upload/page.jpg','label':'Complete source','slices':[{'role':'source_translation','start':0,'end':len(card['headline'])}],'width':1080,'height':1350,'quality':{'status':'passed'}}
        manifest=media.seal_manifest({'version':1,'format':'feed_4_5','card_digest':media.card_digest(card),'pages':[page],'brand_kit':BRAND},1)
        payload={'ig_account_id':1,'source_type':'manual','card_message':card,'media_url':page['url'],'visual_design':{'brand_kit':BRAND,'media_manifest':manifest},'brand_kit':BRAND,'caption_message':{'caption':'Original'},'audience':'new_muslims','purpose':'learn'}
        saved=self.client.post('/api/studio/create-post',json=payload)
        self.assertEqual(saved.status_code,200,saved.text); id=saved.json()['id']
        org=self.db.get(Org,1);org.brand_kit=normalize_brand({'palette':'clay'});self.db.commit()
        payload.update(post_id=id,caption_message={'caption':'Edited caption'})
        self.assertEqual(self.client.post('/api/studio/create-post',json=payload).status_code,200)
        reopened=self.client.get(f'/api/studio/post/{id}').json()
        self.assertEqual(reopened['flags']['media_manifest']['brand_kit'],BRAND)
        self.assertEqual((reopened['target_audience'],reopened['intent_type']),('new_muslims','learn'))
        with patch.object(media,'download_image',return_value=b'fixture'):
            archive=media.export_post(self.db.get(Post,id))
        with zipfile.ZipFile(archive) as z:self.assertEqual(json.loads(z.read('source.json'))['brand_kit'],BRAND)
        payload['brand_kit']=normalize_brand({'palette':'clay'})
        self.assertEqual(self.client.post('/api/studio/create-post',json=payload).status_code,422)
        tampered=deepcopy(manifest);tampered['brand_kit']['signature']='Another author'
        with self.assertRaises(ValueError):media.validate_manifest(tampered,card,1)
    def test_invalid_brand_and_editorial_choices_fail_before_provider_calls(self):
        for kit in ({'palette':'#fff'},{'signature':'x\nInjected'},{'series_name':'🔮'},{'typography':'unbundled'}):
            with self.subTest(kit=kit):self.assertEqual(self.client.put('/api/studio/brand-kit',json={'brand_kit':kit}).status_code,422)
        with patch.object(studio,'generate_visual') as provider:
            self.assertEqual(self.client.post('/api/studio/generate-visual',json={'brand_kit':{'palette':'invalid'}}).status_code,422)
            provider.assert_not_called()
        with self.assertRaises(ValueError):editorial_context('unknown','learn')

class SourceDisplayTests(unittest.TestCase):
    def test_narration_hierarchy_requires_the_exact_reference_and_source_revision(self):
        for field, boundary in (("arabic_text",429),("headline",38)):
            self.assertEqual(narration_boundary(CARD,field),boundary)
            for changed in (dict(CARD,eyebrow="Other source"), {**CARD,field:CARD[field]+" "}):
                self.assertIsNone(narration_boundary(changed,field))
        self.assertIsNone(narration_boundary(CARD,"supporting_text"))

    def test_short_chain_keeps_the_canonical_arabic_and_every_remaining_character(self):
        card=deepcopy(CARD);card['arabic_display']=arabic_display_options(card)[0]
        validate_source_card(card,FIXTURE,'hadith')
        start,end=display_range(card)
        self.assertEqual((start,end),(286,632));self.assertEqual(card['arabic_text'],FIXTURE['arabic_text'])
        self.assertTrue(card['arabic_text'][start:].startswith('عُمَرَ بْنَ الْخَطَّابِ'))
        altered=deepcopy(card);altered['arabic_display']['start']+=1
        with self.assertRaises(ValueError):validate_source_card(altered,FIXTURE,'hadith')
        for field in ('eyebrow','arabic_text'):
            changed=deepcopy(card);changed[field]+=' '
            with self.assertRaises(ValueError):display_range(changed)
        with self.assertRaises(ValueError):validate_source_card(card,FIXTURE,'quran')
        self.assertEqual(arabic_display_options({'eyebrow':'Unmapped hadith','arabic_text':FIXTURE['arabic_text']}),[])
    def test_real_renderer_signs_excerpt_offsets_and_never_hides_other_source_text(self):
        renderer=load_real_service('image_renderer')
        with patch.dict('sys.modules',{'app.services.image_renderer':renderer}):image_card=load_real_service('image_card')
        card=deepcopy(CARD);card['arabic_display']=arabic_display_options(card)[0]
        with tempfile.TemporaryDirectory() as directory,patch.object(settings,'uploads_dir',directory),patch('app.config.build_public_media_url',side_effect=lambda filename,local_path:f'https://res.cloudinary.com/fixture/image/upload/{filename}'):
            data={};image_card.generate_quote_card(card_message=card,style='editorial',allow_sequence=True,render_metadata=data,brand_kit=BRAND)
        manifest=media.seal_manifest(data['media_manifest'],1)
        media.validate_manifest(manifest,card,1)
        slices=[s for p in manifest['pages'] for s in p['slices'] if s['role']=='source_arabic']
        self.assertEqual(slices[0]['start'],286);self.assertEqual(slices[-1]['end'],632)
        self.assertTrue(any('excerpt' in p['label'] for p in manifest['pages']))
        self.assertEqual(manifest['brand_kit'],BRAND)
        bad=deepcopy(manifest);bad['pages'][-1]['slices'][-1]['end']-=1
        bad=media.seal_manifest(bad,1)
        with self.assertRaises(ValueError):media.validate_manifest(bad,card,1)
    def test_no_reflection_mode_uses_no_ai_and_editorial_context_cannot_change_source(self):
        with patch('app.services.llm.generate_card_framing_from_source',return_value={'supporting_text':'Separate thought'}) as ai:
            plain=messages.build_quote_card_message('hadith',FIXTURE,include_reflection=False)
            ai.assert_not_called();self.assertEqual(plain['supporting_text'],'')
            result=messages.build_quote_card_message('hadith',FIXTURE,custom_prompt=editorial_context('new_muslims','learn'))
            self.assertIn('new to learning',ai.call_args.kwargs['custom_prompt'])
            self.assertEqual(result['headline'],FIXTURE['translation_text']);self.assertEqual(result['arabic_text'],FIXTURE['arabic_text'])
            self.assertIsNone(result['hadith_grade'])

class BrandLayoutTests(unittest.TestCase):
    def test_hadith_chain_is_secondary_and_never_occupies_a_separate_leading_page(self):
        for family in ('editorial','quiet_photography','minimal_paper'):
            for fmt in ('feed_4_5','story_9_16'):
                for excerpt in (False,True):
                    with self.subTest(family=family,fmt=fmt,excerpt=excerpt):
                        start=286 if excerpt else 0
                        segments=[{'role':'reference','text':CARD['eyebrow']},
                            {'role':'source_translation','text':CARD['headline'],'narration_end':38},
                            {'role':'source_arabic','text':CARD['arabic_text'][start:],'narration_end':429-start,
                             'label':'Arabic excerpt' if excerpt else None}]
                        kit=normalize_brand({'signature':'@sabeel_studio','series_name':'A moment to reflect'})
                        pages=plan_sequence(segments,family=family,post_format=fmt,brand_kit=kit)
                        self.assertEqual(len(pages),2)
                        for role,expected in (('source_translation',CARD['headline']),('source_arabic',CARD['arabic_text'][start:])):
                            source_segments=[s for p in pages for s in p['segments'] if s['role']==role]
                            self.assertEqual(len(source_segments),1)
                            self.assertEqual(source_segments[0]['text'],expected)
                        for page in pages:
                            _,blocks=layout_card(page['segments'],family=family,post_format=fmt,brand_kit=kit)
                            chain=next(b for b in blocks if b['role']=='narration_context')
                            message=next(b for b in blocks if b['role'] in ('source_arabic','source_translation'))
                            self.assertGreaterEqual(chain['size'],42)
                            self.assertGreater(message['size'],chain['size']*1.25)
                            self.assertLess(chain['bounds'][3],message['bounds'][1])

    def test_brand_and_photo_do_not_strand_a_few_source_words_on_a_continuation(self):
        segments=[{'role':role,'text':FIXTURE[field]} for role,field in
                  [('reference','reference'),('source_translation','translation_text'),('source_arabic','arabic_text')]]
        kit=normalize_brand({'signature':'@sabeel_studio','series_name':'A moment to reflect'})
        pages=plan_sequence(segments,family='quiet_photography',brand_kit=kit)
        for role in ('source_translation','source_arabic'):
            texts=[s['text'] for p in pages for s in p['segments'] if s['role']==role]
            self.assertGreater(len(texts),1)
            self.assertGreaterEqual(min(map(len,texts)),max(map(len,texts))*.5)
        photos=[]
        for page in pages:
            _,blocks=layout_card(page['segments'],family='quiet_photography',brand_kit=kit)
            photos.append(blocks[0]['photo_height'])
        self.assertEqual(len(set(photos)),1)

    def test_identity_text_and_sources_fit_story_safe_area_and_pass_ink_contrast(self):
        segments=[{'role':'reference','text':'Synthetic fixture'},{'role':'source_translation','text':'A source for this layout test.'},{'role':'source_arabic','text':'نص تجريبي'}]
        for palette in PALETTES:
            kit=normalize_brand({**BRAND,'palette':palette,'signature':'سبيل','composition':'airy'})
            size,blocks=layout_card(segments,post_format='story_9_16',brand_kit=kit)
            self.assertTrue(all(250<=b['bounds'][1]<b['bounds'][3]<=1610 for b in blocks))
            roles={b['role'] for b in blocks};self.assertIn('creator_signature',roles);self.assertIn('series_title',roles)
            quality={};paint_card_text(Image.new('RGB',size,PALETTES[palette]['paper']),blocks,brand_kit=kit,quality=quality)
            self.assertTrue(all(b['minimum_contrast']>=4.8 for b in quality['blocks']))
        self.assertGreater(len({composition_for(normalize_brand(),str(i)) for i in range(20)}),1)
    def test_overwide_signature_is_rejected_instead_of_shrunk_or_clipped(self):
        with self.assertRaises(CardTypographyError):layout_card([{'role':'source_translation','text':'Synthetic'}],brand_kit=normalize_brand({'signature':'W'*48}))
