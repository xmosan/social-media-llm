"""Real-font rendering regressions. Text fixtures are not scripture."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageChops
from app.services import card_typography as typography
from test_image_provider import load_real_service


class CardTypographyTests(unittest.TestCase):
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
        self.assertEqual(size, (1080, 1080))
        self.assertEqual(len(blocks), 4)
        for segment, block in zip(segments, blocks):
            self.assertEqual(' '.join(line['text'] for line in block['lines']), segment['text'])
        self.assertEqual(blocks[-1]['label']['text'], 'Reflection')
        background = Image.new('RGB', size, (0, 0, 0))
        result = typography.paint_card_text(background, blocks)
        ink = ImageChops.difference(background, result)
        for i, block in enumerate(blocks):
            left, top, right, bottom = block['bounds']
            self.assertIsNotNone(ink.crop((left-2, top-2, right+2, bottom+2)).getbbox())
            if i:
                previous = blocks[i-1]['bounds'][3]
                self.assertGreaterEqual(top-previous, 32)
                self.assertIsNone(ink.crop((0, previous+3, size[0], top-3)).getbbox())
        self.assertIsNone(ink.crop((0, 0, 90, size[1])).getbbox())
        self.assertIsNone(ink.crop((990, 0, size[0], size[1])).getbbox())

    def test_long_source_uses_portrait_and_does_not_drop_words(self):
        text = 'Synthetic longer translation with source words preserved. ' * 18
        size, blocks = typography.layout_card([{'text': 'Fixture', 'role': 'reference', 'size': 34},
                                               {'text': text, 'role': 'source_translation', 'size': 48}])
        self.assertEqual(size, (1080, 1350))
        self.assertEqual(' '.join(line['text'] for line in blocks[1]['lines']), text.strip())
        self.assertGreaterEqual(blocks[1]['size'], 36)

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
