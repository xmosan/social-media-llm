"""Background receipts reuse stable assets without allowing arbitrary downloads."""
import io
import unittest
from unittest.mock import patch, Mock
from PIL import Image
from app.services import visual_service as visual
from app.services.card_typography import CardTypographyError


class VisualBackgroundReuseTests(unittest.TestCase):
    def request(self, **overrides):
        return visual.VisualRequest(style='quiet_photography', owner_id=7,
                                    custom_prompt='Soft daylight', **overrides)

    def token(self, **overrides):
        data = {'url': 'https://res.cloudinary.com/fixture/image/upload/v1/photo.jpg',
                'owner': 7, 'prompt': visual._hash_prompt('Soft daylight')}
        data.update(overrides)
        return visual._background_signer().dumps(data)

    def test_tampering_cross_workspace_changed_brief_and_external_urls_never_fetch(self):
        tokens = ['forged', self.token(owner=8), self.token(prompt='wrong'),
                  self.token(url='http://127.0.0.1/private'), self.token(url='https://res.cloudinary.com.evil/image/upload/a')]
        with patch('requests.get') as get:
            for token in tokens:
                with self.subTest(token=token[:8]), self.assertRaises(CardTypographyError):
                    visual._load_background(token, self.request())
            get.assert_not_called()

    def test_valid_receipt_decodes_image_without_redirects_and_layout_is_independent(self):
        buf = io.BytesIO(); Image.new('RGB', (18, 22), 'blue').save(buf, 'PNG')
        response = Mock(status_code=200)
        response.iter_content.return_value = [buf.getvalue()]
        response.__enter__ = Mock(return_value=response); response.__exit__ = Mock(return_value=False)
        with patch('requests.get', return_value=response) as get:
            image = visual._load_background(self.token(), self.request(layout='bilingual'))
        self.assertEqual(image.size, (18, 22))
        self.assertFalse(get.call_args.kwargs['allow_redirects'])
        self.assertTrue(get.call_args.kwargs['stream'])

    def test_missing_saved_background_does_not_silently_buy_a_replacement(self):
        response = Mock(status_code=302)
        response.__enter__ = Mock(return_value=response); response.__exit__ = Mock(return_value=False)
        with patch('requests.get', return_value=response), patch('app.services.image_card.generate_quote_card') as render:
            result = visual.generate_visual(self.request(background_token=self.token(), card_message={'headline':'fixture'}))
        self.assertEqual(result.error_status, 422)
        self.assertIn('new photograph', result.error)
        render.assert_not_called()

    def test_facade_reuses_verified_photo_and_returns_design_separately_from_source(self):
        card = {'headline': 'Complete synthetic source', 'arabic_text': 'نص تجريبي', 'supporting_text': 'Separate reflection'}
        original = dict(card)
        def render(**kw):
            self.assertIsNotNone(kw['background_image'])
            self.assertEqual(kw['layout'], 'bilingual')
            kw['render_metadata'].update({'background_reused': True, 'quality': {'status': 'passed'}})
            return 'https://res.cloudinary.com/fixture/image/upload/card.jpg'
        with patch.object(visual, '_load_background', return_value=Image.new('RGB',(10,10))), patch('app.services.image_card.generate_quote_card', side_effect=render):
            result = visual.generate_visual(self.request(background_token='signed-fixture', layout='bilingual', card_message=card))
        self.assertTrue(result.ok)
        self.assertEqual(result.design['background_token'], 'signed-fixture')
        self.assertTrue(result.design['background_reused'])
        self.assertEqual(card, original)
