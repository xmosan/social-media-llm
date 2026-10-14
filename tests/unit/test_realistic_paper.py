"""AI paper shares canonical source, paid-generation and retained-media boundaries."""
import copy
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from app.services import vision_families as catalog, visual_service as visual
from app.services.brand_kit import normalize_brand, DEFAULT_BRAND
from app.services.card_typography import CardTypographyError, layout_card
from test_image_provider import load_real_service


class RealisticPaperTests(unittest.TestCase):
    def test_finishes_validate_without_changing_legacy_snapshots(self):
        self.assertEqual(normalize_brand(), DEFAULT_BRAND)
        self.assertEqual(normalize_brand({'paper_finish':'handmade'}), DEFAULT_BRAND)
        for finish in catalog.PAPER_FINISHES:
            kit=normalize_brand({'family':'realistic_paper','paper_finish':finish})
            self.assertEqual(kit.get('paper_finish','handmade'),finish)
        for value in ('invented',None,{},12):
            with self.assertRaises(ValueError):normalize_brand({'paper_finish':value})

    def test_paper_brief_permits_real_ornament_but_never_scripture_and_rotates(self):
        history={}; bounds=[(120,120,960,1180)]
        for finish in catalog.PAPER_FINISHES:
            prompt,meta=catalog.scene_prompt('realistic_paper',(1080,1350),bounds,paper_finish=finish,direction='White petals, pale blue paper',history=history)
            self.assertIn('White petals, pale blue paper',prompt)
            self.assertIn('no text',prompt.lower())
            self.assertIn(str(meta['text_zones']),prompt)
            self.assertNotIn('gold decoration,',prompt)
            self.assertEqual(meta['paper_finish'],finish)
            history[meta['prompt_signature']]='2026-10-14'
            _,next_meta=catalog.scene_prompt('realistic_paper',(1080,1350),bounds,paper_finish=finish,direction='White petals, pale blue paper',history=history)
            self.assertNotEqual(meta['prompt_signature'],next_meta['prompt_signature'])
        with self.assertRaises(ValueError):catalog.scene_prompt('realistic_paper',(1080,1350),bounds,paper_finish='invalid')

    def test_paper_finish_receipt_binds_before_network_even_with_cache(self):
        url='https://res.cloudinary.com/fixture/image/upload/v1/paper.jpg'
        req=visual.VisualRequest(style='realistic_paper',owner_id=7,brand_kit={'paper_finish':'aged'})
        token=visual._background_signer().dumps({'url':url,'owner':7,'prompt':visual._hash_prompt(''),'recipe':catalog.recipe_binding('realistic_paper','feed_4_5','aged')})
        with visual._preview_lock:visual._preview_photos[(7,url)]=(time.monotonic()+300,Image.new('RGB',(8,8)))
        try:
            with patch('requests.get') as get:
                self.assertEqual(visual._load_background(token,req,use_cache=True).size,(8,8))
                req.brand_kit={'paper_finish':'botanical'}
                with self.assertRaises(CardTypographyError):visual._load_background(token,req,use_cache=True)
                get.assert_not_called()
        finally:
            with visual._preview_lock:visual._preview_photos.clear()
        self.assertEqual(catalog.recipe_binding('luxury_editorial','feed_4_5','aged'),catalog.recipe_binding('luxury_editorial','feed_4_5'))

    def test_paper_sequence_generates_once_and_preserves_every_source_slice(self):
        renderer=load_real_service('image_renderer')
        with patch.dict('sys.modules',{'app.services.image_renderer':renderer}):card=load_real_service('image_card')
        r=json.loads((Path(__file__).parents[1]/'fixtures/hadith_bukhari_1.json').read_text())
        source={'eyebrow':r['reference'],'headline':r['translation_text'],'arabic_text':r['arabic_text']};before=copy.deepcopy(source)
        meta={};brand=normalize_brand({'paper_finish':'manuscript','typography':'classic','signature':'@fixture'})
        with tempfile.TemporaryDirectory() as directory,patch('app.config.build_public_media_url',side_effect=lambda name,local_path:local_path),patch.object(renderer,'generate_background',return_value=Image.new('RGB',(1088,1360),(235,229,212))) as provider:
            card.generate_quote_card(card_message=source,style='realistic_paper',brand_kit=brand,allow_sequence=True,render_metadata=meta,output_dir=directory)
            provider.assert_called_once();prompt=provider.call_args.args[0]
            self.assertIn('gold-leaf',prompt)
            for text in source.values():self.assertNotIn(text,prompt)
            self.assertGreater(len(meta['media_manifest']['pages']),1)
            for role,field in [('source_arabic','arabic_text'),('source_translation','headline')]:
                self.assertEqual(''.join(source[field][s['start']:s['end']] for p in meta['media_manifest']['pages'] for s in p['slices'] if s['role']==role),source[field])
            for p in meta['media_manifest']['pages']:self.assertGreaterEqual(p['quality']['encoded_minimum_contrast'],4.5)
        self.assertEqual(source,before)

    def test_edge_clearance_is_measured_before_generation(self):
        for fmt in ('feed_4_5','story_9_16'):
            size,blocks=layout_card([{'role':'source_translation','text':'Synthetic fixture.'}],family='realistic_paper',post_format=fmt,brand_kit={'composition':'anchored'})
            self.assertTrue(all(b['bounds'][0]>=120 and b['bounds'][2]<=960 for b in blocks))
