"""Editing previews never create publishable assets or purchase backgrounds."""
import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from app.services import visual_service as visual
from app.services.card_typography import CardTypographyError
from test_image_provider import load_real_service


class VisualPreviewTests(unittest.TestCase):
    def test_preview_requires_saved_photo_and_never_calls_provider(self):
        with patch('app.services.image_card.generate_quote_card') as render:
            for family in ('luxury_editorial', 'quiet_photography', 'unknown'):
                with self.assertRaises(CardTypographyError):
                    visual.preview_visual(visual.VisualRequest(style=family, card_message={'headline':'Synthetic fixture'}))
            render.assert_not_called()

    def test_receipt_is_revalidated_even_when_cached(self):
        from app.services.vision_families import recipe_binding
        request=visual.VisualRequest(style='midnight_oasis',owner_id=7,card_message={'headline':'Fixture'})
        url='https://res.cloudinary.com/fixture/image/upload/v1/preview.jpg'
        import time
        with visual._preview_lock:
            visual._preview_photos[(7,url)]=(time.monotonic()+300,Image.new('RGB',(8,8)))
        data={'url':url,'owner':7,'prompt':visual._hash_prompt(''),'recipe':recipe_binding('midnight_oasis','feed_4_5')}
        with patch('requests.get') as get:
            token=visual._background_signer().dumps(data)
            self.assertEqual(visual._load_background(token,request,use_cache=True).size,(8,8))
            request.owner_id=8
            with self.assertRaises(CardTypographyError):visual._load_background(token,request,use_cache=True)
            get.assert_not_called()
        with visual._preview_lock:visual._preview_photos.clear()

    def test_real_preview_uses_final_layout_without_upload_or_manifest(self):
        # The broader suite deliberately stubs providers; restore just the real
        # compositor modules for these measured image assertions.
        renderer = load_real_service('image_renderer')
        import sys
        with patch.dict(sys.modules, {'app.services.image_renderer': renderer}):
            card_renderer = load_real_service('image_card')
        with patch.dict(sys.modules, {'app.services.image_card': card_renderer}):
            source=json.loads((Path(__file__).parents[1]/'fixtures/quran_13_28.json').read_text())
            card={'eyebrow':source['reference'],'arabic_text':source['arabic_text'],'headline':source['translation_text'],'supporting_text':''}
            original=dict(card)
            request=visual.VisualRequest(style='midnight_oasis',owner_id=7,card_message=card,background_token='fixture',brand_kit={'typography':'classic'})
            with patch.object(visual,'_load_background',return_value=Image.new('RGB',(1080,1350),(35,45,55))), patch('app.config.build_public_media_url') as upload, patch.object(renderer,'generate_background') as ai:
                result=visual.preview_visual(request)
                upload.assert_not_called();ai.assert_not_called()
            self.assertTrue(result['preview_only']);self.assertNotIn('media_manifest',result)
            self.assertEqual(result['page_count'],1);self.assertEqual(card,original)
            preview=base64.b64decode(result['image_data'].split(',',1)[1])
            self.assertEqual(Image.open(io.BytesIO(preview)).size,(1080,1350))
            with tempfile.TemporaryDirectory() as directory, patch('app.config.build_public_media_url',side_effect=lambda name,local_path:local_path):
                meta={}
                final=card_renderer.generate_quote_card(card_message=card,style=request.style,brand_kit=request.brand_kit,background_image=Image.new('RGB',(1080,1350),(35,45,55)),allow_sequence=True,render_metadata=meta,output_dir=directory)
                self.assertEqual(Path(final).read_bytes(),preview)

    def test_long_source_preview_paginates_without_changing_source_or_publishing(self):
        renderer=load_real_service('image_renderer')
        import sys
        with patch.dict(sys.modules,{'app.services.image_renderer':renderer}):
            card_renderer=load_real_service('image_card')
        card={'eyebrow':'Synthetic source','arabic_text':'نص تجريبي للقراءة. '*32,'headline':'A complete synthetic source for testing layout preservation. '*20}
        original=dict(card)
        with patch.dict(sys.modules,{'app.services.image_card':card_renderer}), patch('app.config.build_public_media_url') as upload, patch.object(renderer,'generate_background') as ai:
            req=visual.VisualRequest(style='editorial',card_message=card,post_format='story_9_16')
            first=visual.preview_visual(req)
            self.assertGreater(first['page_count'],1)
            last=visual.preview_visual(req,first['page_count']-1)
            self.assertEqual(last['page_index'],first['page_count']-1)
            self.assertEqual(last['page_count'],first['page_count'])
            with self.assertRaises(ValueError):visual.preview_visual(req,first['page_count'])
            upload.assert_not_called();ai.assert_not_called()
        self.assertEqual(card,original)

    def test_preview_busy_does_not_queue_expensive_work(self):
        with patch.object(visual,'_preview_slots') as slots:
            slots.acquire.return_value=False
            with self.assertRaises(visual.PreviewBusyError):
                visual.preview_visual(visual.VisualRequest(style='editorial',card_message={'headline':'Synthetic fixture'}))
            slots.release.assert_not_called()
