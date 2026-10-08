"""Scene eligibility, actual delivery contrast and shared canonical routing."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from PIL import Image, ImageDraw
from app.services import card_typography as typography
from app.services import vision_families as catalog
from app.services.brand_kit import normalize_brand
from test_image_provider import load_real_service


class VisionFamilyTests(unittest.TestCase):
    def test_nature_blocks_dense_source_before_provider_and_keeps_short_source_exact(self):
        renderer = load_real_service('image_renderer')
        record=json.loads((Path(__file__).resolve().parents[1]/'fixtures/hadith_bukhari_1.json').read_text())
        segments=[{'role':role,'text':record[key]} for role,key in [('reference','reference'),('source_translation','translation_text'),('source_arabic','arabic_text')]]
        with patch.dict('sys.modules',{'app.services.image_renderer':renderer}):
            card=load_real_service('image_card')
        with patch.object(renderer,'generate_background') as generate:
            with self.assertRaisesRegex(typography.CardTypographyError,'Quiet Nature'):
                card.generate_quote_card(card_message={'eyebrow':record['reference'],'headline':record['translation_text'],'arabic_text':record['arabic_text']},
                                         style='emerald_forest',allow_sequence=True,render_metadata={})
            generate.assert_not_called()
        short=[{'role':'source_translation','text':'A short synthetic source.'},{'role':'reference','text':'Fixture'}]
        for fmt in ('feed_4_5','story_9_16'):
            size,blocks=typography.layout_card(short,family='emerald_forest',post_format=fmt)
            self.assertEqual(' '.join(blocks[0]['lines'][i]['text'] for i in range(len(blocks[0]['lines']))),short[0]['text'])
            self.assertLessEqual(max(b['bounds'][3] for b in blocks), size[1]*(.65 if fmt=='story_9_16' else .75))

    def test_scene_sequence_uses_one_portrait_background_and_combined_page_bounds(self):
        renderer=load_real_service('image_renderer')
        with patch.dict('sys.modules',{'app.services.image_renderer':renderer}):
            card=load_real_service('image_card')
        source={'eyebrow':'Synthetic reference','headline':'A synthetic paragraph, complete and exact. '*15,'arabic_text':'نص تجريبي فقط. '*25}
        metadata={}; retained=Mock()
        with tempfile.TemporaryDirectory() as directory, patch('app.config.settings.uploads_dir',directory), \
             patch('app.config.build_public_media_url',side_effect=lambda name,local_path:'https://res.cloudinary.com/fixture/image/upload/'+name), \
             patch.object(renderer,'generate_background',return_value=Image.new('RGB',(1080,1920),(220,221,222))) as provider:
            # scene_prompt is imported locally from the catalog, intentionally.
            with patch.object(catalog,'scene_prompt',wraps=catalog.scene_prompt) as prompt:
                card.generate_quote_card(card_message=source,style='luxury_editorial',allow_sequence=True,post_format='story_9_16',
                                         render_metadata=metadata,background_sink=retained)
        provider.assert_called_once();retained.assert_called_once()
        self.assertEqual(provider.call_args.kwargs['provider_size'],'1152x2048')
        self.assertGreater(len(metadata['media_manifest']['pages']),1)
        self.assertGreater(len(prompt.call_args.args[2]),len(metadata['card_layout']['blocks']))
        from app.services.media_sequence import seal_manifest,validate_manifest
        validate_manifest(seal_manifest(metadata['media_manifest'],7),source,7)
        for page in metadata['media_manifest']['pages']:
            self.assertGreaterEqual(page['quality']['encoded_minimum_contrast'],4.5)
            self.assertLessEqual(page['quality']['wash_opacity'],.2)
            self.assertTrue(page['quality']['review_required'])

    def test_bad_scene_is_retained_but_never_uploaded_as_a_finished_card(self):
        renderer=load_real_service('image_renderer')
        raw=Image.new('RGB',(1080,1350),'white'); draw=ImageDraw.Draw(raw)
        for x in range(0,1080,16):draw.rectangle((x,0,x+7,1349),fill='black')
        sink=Mock()
        with tempfile.TemporaryDirectory() as directory, patch.object(renderer,'generate_background',return_value=raw), \
             patch('app.config.build_public_media_url') as upload:
            with self.assertRaisesRegex(typography.CardTypographyError,'readability'):
                renderer.render_minimal_quote_card([{'role':'source_translation','text':'Complete synthetic source.'}],directory,
                    style='luxury_editorial',mode='scene',background_sink=sink)
            sink.assert_called_once();upload.assert_not_called()

    def test_delivery_gate_catches_corrupted_text_after_encoding(self):
        size,blocks=typography.layout_card([{'role':'source_translation','text':'Synthetic readability fixture'}])
        background=Image.new('RGB',size,'white'); quality={}
        result=typography.paint_card_text(background,blocks,quality=quality,wash_limit=.2,strong_ink=True)
        typography.check_encoded_contrast(result,background,blocks,quality)
        with self.assertRaisesRegex(typography.CardTypographyError,'final image'):
            typography.check_encoded_contrast(background,background,blocks,quality)

    def test_encoding_repair_is_bounded_and_never_buys_another_background(self):
        renderer=load_real_service('image_renderer');metadata={}
        with tempfile.TemporaryDirectory() as directory, patch.object(renderer,'generate_background',return_value=Image.new('RGB',(1080,1350),'white')) as provider, \
             patch.object(typography,'check_encoded_contrast',side_effect=[typography.CardTypographyError('Encoding failed'),None]) as check, \
             patch('app.config.build_public_media_url',return_value='https://res.cloudinary.com/fixture/image/upload/card.jpg'):
            renderer.render_minimal_quote_card([{'role':'source_translation','text':'Synthetic complete source.'}],directory,
                style='luxury_editorial',mode='scene',render_metadata=metadata)
        provider.assert_called_once();self.assertEqual(check.call_count,2)
        self.assertEqual(metadata['quality']['wash_opacity'],.1)
        with tempfile.TemporaryDirectory() as directory, patch.object(renderer,'generate_background',return_value=Image.new('RGB',(1080,1350),'white')) as provider, \
             patch.object(typography,'check_encoded_contrast',side_effect=typography.CardTypographyError('Encoding failed')) as check, \
             patch('app.config.build_public_media_url') as upload:
            with self.assertRaises(typography.CardTypographyError):
                renderer.render_minimal_quote_card([{'role':'source_translation','text':'Synthetic complete source.'}],directory,
                    style='luxury_editorial',mode='scene',render_metadata=metadata)
            self.assertFalse(list(Path(directory).glob('*.jpg')))
        provider.assert_called_once();upload.assert_not_called();self.assertEqual(check.call_count,3)
        self.assertEqual(metadata['quality']['wash_opacity'],.2)

    def test_history_rotates_variants_and_exhaustion_uses_least_recent(self):
        bounds=[(80,80,1000,950)];history={}
        for i in range(96):
            prompt,meta=catalog.scene_prompt('luxury_editorial',(1080,1350),bounds,history=history)
            self.assertNotIn(meta['prompt_signature'],history)
            history[meta['prompt_signature']]=f'{i:03}'
            self.assertIn(str(meta['text_zones']),prompt)
        _,meta=catalog.scene_prompt('luxury_editorial',(1080,1350),bounds,history=history)
        self.assertEqual(meta['prompt_signature'],min(history,key=history.get))

    def test_creator_lighting_precedes_defaults_and_preferences_are_separate_from_source(self):
        for family in catalog.SCENE_FAMILIES:
            prompt, meta = catalog.scene_prompt(family, (1080,1920), [(80,260,1000,800)],
                direction="night light", visual_identity="Coastal views, muted blue. Avoid buildings.")
            self.assertIn('"this_post": "night light"', prompt)
            self.assertIn('Coastal views', prompt)
            self.assertNotIn(catalog.SCENE_FAMILIES[family]['default_light'], prompt)
            self.assertNotIn('evenly pale', prompt)
            self.assertIn("this post's direction, then account preferences", prompt)
            self.assertEqual(meta['prompt_version'], 3)
        with patch.object(catalog.secrets, 'choice', side_effect=lambda options: options[0]):
            _, first = catalog.scene_prompt('emerald_forest',(1080,1350),[(80,80,1000,750)], visual_identity='Coast')
            _, second = catalog.scene_prompt('emerald_forest',(1080,1350),[(80,80,1000,750)], visual_identity='Woodlands')
        self.assertNotEqual(first['prompt_signature'],second['prompt_signature'])

    def test_catalog_and_automation_routing_agree_and_brand_preserves_legacy(self):
        service=load_real_service('automation_service')
        runner=load_real_service('automation_runner')
        from app.routes.ui_assets import STUDIO_COMPONENTS_HTML, STUDIO_SCRIPTS_JS
        for key,spec in catalog.SCENE_FAMILIES.items():
            self.assertEqual(normalize_brand({'family':key})['family'],key)
            self.assertEqual(service.FAMILY_TO_SCENE_KEY[key],runner.FAMILY_TO_SCENE_KEY[key])
            self.assertEqual(service.SYSTEM_STYLE_DNA_PRESETS[key].family,key)
            self.assertIn(spec['label'],STUDIO_COMPONENTS_HTML)
            self.assertIn("'"+key+"'",STUDIO_SCRIPTS_JS)
        self.assertEqual(normalize_brand()['family'],'editorial')
        self.assertEqual(runner.FAMILY_TO_SCENE_KEY['parchment_manuscript'],'parchment_manuscript')
