"""Real-font rendering regressions. Text fixtures are not scripture."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageChops
from app.services import card_typography as typography
from test_image_provider import load_real_service


class CardTypographyTests(unittest.TestCase):
    def test_pause_marks_cannot_be_stranded_by_line_or_page_breaks(self):
        import json
        import unicodedata
        source = next(s for s in json.loads((Path(__file__).resolve().parents[1]/'quality/sources.json').read_text())
                      if s['key']=='quran_medium')['record']['arabic_text']
        font = typography.load_font(source, 68)
        for width in (500, 872, 920):
            lines = typography.wrap(source,font,width)
            self.assertEqual(' '.join(line['text'] for line in lines), source)
            self.assertFalse(any(unicodedata.category(line['text'][0]).startswith('M') for line in lines))
        # The source remains exact, including the provider's space before ۚ.
        for end in typography.source_word_ends(source):
            self.assertTrue(end==len(source) or not unicodedata.category(source[end]).startswith('M'))
        self.assertIn(' ۚ ',source)

    def test_sequence_keeps_combining_marks_with_previous_source_slice(self):
        import unicodedata
        source = 'نَصٌّ تَجْرِيبِيٌّ ۚ غَيْرُ قُرْآنِيٍّ. ' * 30
        segments=[{'role':'reference','text':'Synthetic fixture only'}, {'role':'source_arabic','text':source}]
        pages=typography.plan_sequence(segments,post_format='feed_4_5')
        parts=[source[s['start']:s['end']] for page in pages for s in page['slices']]
        self.assertGreater(len(parts),1)
        self.assertEqual(''.join(parts),source)
        self.assertFalse(any(unicodedata.category(part[0]).startswith('M') for part in parts))

    def test_sequence_continuations_keep_one_type_size_despite_different_lengths(self):
        segments=[{'role':'reference','text':'Synthetic fixture only'},
                  {'role':'source_translation','text':'A synthetic paragraph with changing page lengths. '*30}]
        pages=typography.plan_sequence(segments,post_format='story_9_16')
        self.assertGreater(len(pages),1)
        sizes=set()
        for page in pages:
            _,blocks=typography.layout_card(page['segments'],post_format='story_9_16')
            sizes.update(block['size'] for block in blocks if block['role']=='source_translation')
        self.assertEqual(sizes,{67})

    def test_honorific_uses_a_real_glyph_without_reversing_english(self):
        text = 'Synthetic English (ﷺ) typography fixture.'
        font = typography.load_font(text, 42)
        self.assertEqual(Path(font.path).name, 'Amiri-Regular.ttf')
        self.assertNotEqual(bytes(font.getmask('ﷺ')), bytes(font.getmask('\uffff')))
        self.assertEqual(typography.display_text(text), text)
        self.assertTrue(typography.contains_arabic('ﷺ'))

    def test_missing_native_shaping_fails_clearly(self):
        with patch.object(typography.features, 'check_feature', return_value=False), self.assertRaisesRegex(ValueError, 'shaping is unavailable'):
            typography.load_font('ﷺ', 42)

    def test_wrapped_mixed_text_retains_paragraph_direction_and_original_marks(self):
        text = 'Synthetic text (ﷺ) with punctuation.'
        font = typography.load_font(text, 42)
        lines = typography.wrap(text, font, 160)
        self.assertTrue(all(line['direction'] == 'ltr' for line in lines))
        arabic = 'نَصٌّ تَجْرِيبِيٌّ غَيْرُ قُرْآنِيٍّ'
        lines = typography.wrap(arabic, typography.load_font(arabic, 60), 300)
        self.assertEqual(' '.join(line['display'] for line in lines), arabic)
        self.assertTrue(all(line['direction'] == 'rtl' for line in lines))

    def test_missing_required_font_fails_instead_of_substituting(self):
        with self.assertRaisesRegex(ValueError, 'font is unavailable'):
            typography.load_font('ﷺ', 42, arabic_path='/missing-font.ttf')

    def test_all_blocks_and_case_preserved_with_nonoverlapping_ink(self):
        segments = [{'text': 'Fixture Reference', 'role': 'reference', 'size': 34},
                    {'text': 'نَصٌّ تَجْرِيبِيٌّ غَيْرُ قُرْآنِيٍّ', 'role': 'source_arabic', 'size': 60},
                    {'text': 'Exact synthetic Translation (ﷺ).', 'role': 'source_translation', 'size': 48},
                    {'text': 'Separate generated reflection fixture.', 'role': 'reflection', 'size': 42}]
        size, blocks = typography.layout_card(segments)
        self.assertEqual(size, (1080, 1350))
        self.assertEqual(len(blocks), 4)
        for block in blocks:
            segment = next(s for s in segments if s["role"] == block["role"])
            self.assertEqual(' '.join(line['text'] for line in block['lines']), segment['text'])
        self.assertEqual(next(b for b in blocks if b['role'] == 'reflection')['label']['text'], 'Reflection')
        background = Image.new('RGB', size, (0, 0, 0))
        result = typography.paint_card_text(background, blocks)
        ink = ImageChops.difference(background, result)
        for i, block in enumerate(blocks):
            left, top, right, bottom = block['bounds']
            self.assertIsNotNone(ink.crop((left-2, top-2, right+2, bottom+2)).getbbox())
            if i:
                previous = blocks[i-1]['bounds'][3]
                self.assertGreaterEqual(top-previous, 32)
        self.assertIsNone(ink.crop((0, 0, 82, size[1])).getbbox())
        self.assertIsNone(ink.crop((998, 0, size[0], size[1])).getbbox())

    def test_long_source_uses_portrait_and_does_not_drop_words(self):
        text = 'Synthetic longer translation with source words preserved. ' * 6
        size, blocks = typography.layout_card([{'text': 'Fixture', 'role': 'reference', 'size': 34},
                                               {'text': text, 'role': 'source_translation', 'size': 48}])
        self.assertEqual(size, (1080, 1350))
        self.assertEqual(' '.join(line['text'] for line in next(b for b in blocks if b['role'] == 'source_translation')['lines']), text.strip())
        self.assertGreaterEqual(next(b for b in blocks if b['role'] == 'source_translation')['size'], 52)

    def test_unrenderable_source_fails_before_paid_background_generation(self):
        renderer = load_real_service('image_renderer')
        with tempfile.TemporaryDirectory() as directory, patch.object(renderer, 'generate_background') as generate:
            for text in ('unbroken' * 500, 'Long synthetic source. ' * 500):
                with self.subTest(text=text[:20]), self.assertRaisesRegex(ValueError, 'too long'):
                    renderer.render_minimal_quote_card([{'text': text, 'size': 48}], directory,
                                                       mode='custom', visual_prompt='fixture')
            generate.assert_not_called()

    def test_structured_and_legacy_card_paths_never_limit_to_three_blocks(self):
        renderer = load_real_service('image_renderer')
        with patch.dict('sys.modules', {'app.services.image_renderer': renderer}):
            card = load_real_service('image_card')
        with patch.object(card, 'render_minimal_quote_card', return_value='fixture.jpg') as render:
            card.generate_quote_card(card_message={'eyebrow': 'Reference', 'arabic_text': 'نص تجريبي',
                                                   'headline': 'Synthetic (ﷺ)', 'supporting_text': 'Reflection'})
            segments = render.call_args.args[0]
            self.assertEqual([s['role'] for s in segments], ['reference', 'source_arabic', 'source_translation', 'reflection'])
            self.assertTrue(segments[2]['is_arabic'])
            card.generate_quote_card(caption='First\n\nSecond\n\nThird\n\nFourth')
            self.assertEqual(len(render.call_args.args[0]), 4)

    def test_actual_long_provider_hadith_requires_sequence_without_mutation(self):
        import json
        record = json.loads((Path(__file__).resolve().parents[1] / 'fixtures' / 'hadith_bukhari_1.json').read_text())
        reflection = 'Before your next decision, pause to name what you hope to gain. Honest reflection can reveal the difference between what you value and what you want others to notice.'
        segments = [{'text': record['reference'], 'role': 'reference', 'size': 34},
                    {'text': record['arabic_text'], 'role': 'source_arabic', 'size': 60},
                    {'text': record['translation_text'], 'role': 'source_translation', 'size': 42},
                    {'text': reflection, 'role': 'reflection', 'size': 42}]
        original = [dict(s) for s in segments]
        with self.assertRaisesRegex(typography.CardTypographyError, 'multi-card sequence'):
            typography.layout_card(segments)
        self.assertEqual(segments, original)

    def test_excerpt_label_is_visible_without_modifying_source_text(self):
        text = 'Exact provider excerpt fixture.'
        size, blocks = typography.layout_card([{'text': text, 'role': 'source_translation', 'label': 'Translation excerpt', 'size': 42}])
        self.assertEqual(blocks[0]['label']['text'], 'Translation excerpt')
        self.assertEqual(' '.join(line['text'] for line in blocks[0]['lines']), text)

    def test_facade_exposes_only_safe_card_errors_and_route_uses_422(self):
        import json
        from app.services import visual_service
        from app.routes.studio import studio_generate_visual
        error = typography.CardTypographyError('Choose a shorter source or remove the optional reflection.')
        with patch.object(visual_service, '_generate_quote_card', side_effect=error):
            result = visual_service.generate_visual(visual_service.VisualRequest(card_message={'headline': 'fixture'}))
        self.assertEqual(result.error, str(error))
        self.assertEqual(result.error_status, 422)
        with patch('app.routes.studio.generate_visual', return_value=result):
            response = studio_generate_visual({'card_message': {'headline': 'fixture'}, 'brand_kit': {}})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(json.loads(response.body)['error'], str(error))
        with patch.object(visual_service, '_generate_quote_card', side_effect=ValueError('private provider response')):
            result = visual_service.generate_visual(visual_service.VisualRequest(card_message={'headline': 'fixture'}))
        self.assertNotIn('private', result.error)


    def test_local_contrast_repairs_bright_pixels_directly_beneath_dark_ink(self):
        size, blocks = typography.layout_card([{'text': 'Local contrast fixture', 'role': 'source_translation'}])
        mask = typography._ink_mask(size, blocks[0], 'Left')
        # A background with near-identical global brightness but alternating dark
        # and light stripes under real letters defeats average-luma selection.
        background = Image.new('RGB', size, (245, 245, 245))
        from PIL import ImageDraw
        draw = ImageDraw.Draw(background)
        for x in range(90, 990, 16):
            draw.rectangle((x, 100, x+7, 1100), fill=(15, 25, 20))
        quality = {}
        result = typography.paint_card_text(background, blocks, quality=quality)
        self.assertTrue(quality['background_repaired'])
        self.assertTrue(all(b['minimum_contrast'] >= 4.8 for b in quality['blocks']))
        self.assertEqual(result.size, size)

    def test_both_reading_orders_keep_every_verified_source_character(self):
        import json
        record = json.loads((Path(__file__).resolve().parents[1] / 'fixtures/quran_94_6.json').read_text())
        segments = [{'role': role, 'text': record[key]} for role, key in
                    [('reference', 'reference'), ('source_arabic', 'arabic_text'), ('source_translation', 'translation_text')]]
        for family in typography.DESIGN_FAMILIES:
            for layout in typography.FEED_LAYOUTS:
                size, blocks = typography.layout_card(segments, family=family, layout=layout)
                self.assertEqual(size, (1080, 1350))
                self.assertEqual(blocks[0]['role'], 'source_translation' if layout == 'english_first' else 'source_arabic')
                for b in blocks:
                    self.assertEqual(' '.join(l['text'] for l in b['lines']), next(s['text'] for s in segments if s['role'] == b['role']))
                    self.assertLessEqual(b['bounds'][3], 1262)

    def test_simple_designs_need_no_image_provider_and_photo_layout_reuses_input(self):
        renderer = load_real_service('image_renderer')
        segments = [{'text': 'Synthetic complete source', 'role': 'source_translation'}]
        with tempfile.TemporaryDirectory() as directory, patch.object(renderer, 'generate_background') as generate, patch('app.config.build_public_media_url', side_effect=lambda filename, local_path: local_path):
            for family in ('editorial', 'minimal_paper', 'quiet_photography'):
                metadata = {}
                path = renderer.render_minimal_quote_card(segments, directory, style=family, mode='scene',
                    background_image=Image.new('RGB', (1080, 1080), 'blue'), render_metadata=metadata)
                self.assertTrue(Path(path).is_file())
                self.assertEqual(metadata['quality']['status'], 'passed')
            generate.assert_not_called()
