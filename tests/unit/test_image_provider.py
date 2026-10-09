import base64
from contextlib import nullcontext
from io import BytesIO
from types import SimpleNamespace
import unittest
import importlib.util
from pathlib import Path
import sys
import tempfile
from unittest.mock import Mock, patch

from PIL import Image
import requests

from app.services import image_provider as provider
from app.config import settings


def fixture_image():
    buffer = BytesIO()
    Image.new("RGB", (16, 16), (20, 30, 40)).save(buffer, "PNG")
    return base64.b64encode(buffer.getvalue()).decode()


class ImageProviderTests(unittest.TestCase):
    def setUp(self):
        for stub in (patch("app.services.usage_limits.paid_call", side_effect=lambda kind: nullcontext()), patch.object(settings, "openai_api_key", "fixture")):
            stub.start(); self.addCleanup(stub.stop)

    def test_portrait_size_is_retained_through_provider_fallback(self):
        result = provider.GeneratedImage(Image.new('RGB', (16, 16)), 'openai', settings.openai_image_fallback_model)
        with patch.object(provider, 'generate_openai_image', side_effect=[provider.ImageGenerationError('unavailable', 404), result]) as generate:
            provider.generate_configured_image('fixture', size='1152x2048')
        self.assertEqual([call.kwargs['size'] for call in generate.call_args_list], ['1152x2048', '1152x2048'])

    def test_invalid_dimensions_fail_before_a_paid_call(self):
        with patch.object(provider, 'OpenAI') as client:
            with self.assertRaisesRegex(provider.ImageGenerationError, 'unsupported_image_size'):
                provider.generate_openai_image('fixture', api_key='fixture', model='fixture', size='99999x99999')
        client.assert_not_called()

    def test_openai_receives_exact_portrait_dimensions(self):
        with patch.object(provider, 'OpenAI') as client:
            api = client.return_value.__enter__.return_value
            api.images.generate.return_value = SimpleNamespace(data=[SimpleNamespace(b64_json=fixture_image())], usage=None)
            provider.generate_openai_image('fixture', api_key='fixture', model='fixture', size='1088x1360')
        self.assertEqual(api.images.generate.call_args.kwargs['size'], '1088x1360')

    def test_openai_uses_gpt_image_bytes_and_disables_automatic_paid_retries(self):
        with patch.object(provider, "OpenAI") as client:
            api = client.return_value.__enter__.return_value
            api.images.generate.return_value = SimpleNamespace(
                data=[SimpleNamespace(b64_json=fixture_image())], usage=None)
            result = provider.generate_openai_image("fixture", api_key="fixture-key", model="gpt-image-2.5-flare")
        self.assertEqual(result.image.size, (16, 16))
        self.assertEqual(result.model, "gpt-image-2.5-flare")
        self.assertEqual(client.call_args.kwargs["max_retries"], 0)
        kwargs = api.images.generate.call_args.kwargs
        self.assertEqual(kwargs["quality"], "medium")
        self.assertEqual(kwargs["n"], 1)
        self.assertNotIn("response_format", kwargs)

    def test_google_uses_current_interactions_schema_and_header_auth(self):
        response = Mock()
        response.json.return_value = {"output_image": {"data": fixture_image()}, "usage": {"total_tokens": 1}}
        with patch.object(provider.requests, "post", return_value=response) as post:
            result = provider.generate_google_image("fixture", api_key="fixture-key", model="gemini-nano-banana-2.1")
        self.assertEqual(result.image.size, (16, 16))
        self.assertNotIn("fixture-key", post.call_args.args[0])
        self.assertEqual(post.call_args.kwargs["headers"]["x-goog-api-key"], "fixture-key")
        self.assertFalse(post.call_args.kwargs["json"]["store"])
        self.assertEqual(post.call_args.kwargs["json"]["response_format"]["image_size"], "1K")

    def test_invalid_or_empty_image_fails_clearly(self):
        for data in (None, "", "not base64", base64.b64encode(b"not an image").decode()):
            with self.subTest(data=data), self.assertRaises(provider.ImageGenerationError):
                provider.decode_image(data)
        response = Mock()
        response.json.return_value = {"status": "completed"}
        with patch.object(provider.requests, "post", return_value=response), self.assertRaises(provider.ImageGenerationError):
            provider.generate_google_image("fixture", api_key="fixture-key", model="gemini-3-pro-image")

    def test_provider_errors_do_not_expose_response_or_credentials(self):
        with patch.object(provider, "OpenAI", side_effect=RuntimeError("private-provider-detail")):
            with self.assertRaises(provider.ImageGenerationError) as caught:
                provider.generate_openai_image("fixture", api_key="fixture-key", model="fixture")
        self.assertNotIn("private-provider-detail", str(caught.exception))
        with patch.object(provider.requests, "post", side_effect=requests.Timeout("private-provider-detail")):
            with self.assertRaises(provider.ImageGenerationError) as caught:
                provider.generate_google_image("fixture", api_key="fixture-key", model="fixture")
        self.assertNotIn("private-provider-detail", str(caught.exception))

    def test_missing_credentials_do_not_make_requests(self):
        with patch.object(provider, "OpenAI") as openai, patch.object(provider.requests, "post") as google:
            for generate in (provider.generate_openai_image, provider.generate_google_image):
                with self.assertRaises(provider.ImageGenerationError):
                    generate("fixture", api_key=None, model="fixture")
        openai.assert_not_called()
        google.assert_not_called()

    def test_eligible_failure_uses_exactly_one_configured_fallback(self):
        image = provider.GeneratedImage(Image.new("RGB", (16, 16)), "openai", settings.openai_image_fallback_model)
        with patch.object(provider, "generate_openai_image", side_effect=[provider.ImageGenerationError("unavailable", 404), image]) as generate:
            result = provider.generate_configured_image("fixture")
        self.assertIs(result, image)
        self.assertEqual([c.kwargs["model"] for c in generate.call_args_list],
                         [settings.openai_image_model, settings.openai_image_fallback_model])

    def test_timeouts_auth_refusals_and_bad_images_never_trigger_fallback(self):
        for status in (None, 400, 401, 402, 403, 500, 504):
            with self.subTest(status=status), patch.object(provider, "generate_openai_image", side_effect=provider.ImageGenerationError("failed", status)) as generate:
                with self.assertRaises(provider.ImageGenerationError):
                    provider.generate_configured_image("fixture")
                generate.assert_called_once()

    def test_historical_google_label_does_not_call_google_in_production(self):
        with patch.object(provider, "generate_openai_image") as openai, patch.object(provider, "generate_google_image") as google:
            provider.generate_configured_image("fixture", engine="gemini")
        openai.assert_called_once()
        google.assert_not_called()

    def test_model_and_quality_change_cache_identity(self):
        before = provider.configured_image_cache_key()
        with patch.object(settings, "openai_image_quality", "high"):
            self.assertNotEqual(provider.configured_image_cache_key(), before)
        with patch.object(settings, "openai_image_model", "gpt-image-2.5-flare"):
            self.assertNotEqual(provider.configured_image_cache_key(), before)


def load_real_service(name):
    path = Path(__file__).resolve().parents[2] / "app" / "services" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"image_test_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ImageIntegrationTests(unittest.TestCase):
    def test_readability_halo_has_no_rectangular_tile_seam(self):
        renderer = load_real_service("image_renderer")
        image = renderer.draw_radial_halo(Image.new("RGB", (400, 400), (50, 50, 50)),
                                          (200, 200), 100, (255, 255, 255), 100)
        # The former tile began at x=100 and jumped abruptly from no veil to a veil.
        pixels = [image.getpixel((x, 200))[0] for x in range(90, 111)]
        self.assertLessEqual(max(abs(a-b) for a, b in zip(pixels, pixels[1:])), 2)
        self.assertGreater(image.getpixel((200, 200))[0], image.getpixel((0, 0))[0])

    def test_legacy_image_url_is_real_jpeg_uploaded_to_cloudinary(self):
        llm = load_real_service("llm")
        result = provider.GeneratedImage(Image.new("RGB", (16, 16)), "openai", "fixture-model")
        with tempfile.TemporaryDirectory() as directory, patch.object(settings, "uploads_dir", directory), \
             patch.object(provider, "generate_configured_image", return_value=result), \
             patch("app.services.cloudinary_service.upload_to_cloudinary", return_value="https://res.cloudinary.com/fixture/image/upload/a.jpg") as upload:
            url = llm.generate_ai_image("fixture")
            self.assertTrue(url.startswith("https://res.cloudinary.com/"))
            with Image.open(upload.call_args.args[0]) as image:
                self.assertEqual(image.format, "JPEG")
            upload.return_value = None
            self.assertIsNone(llm.generate_ai_image("fixture"))

    def test_renderer_uses_shared_provider_and_records_actual_model(self):
        renderer = load_real_service("image_renderer")
        result = provider.GeneratedImage(Image.new("RGB", (16, 16)), "openai", "gpt-image-2.5-flare")
        metadata = {}
        with patch.object(renderer, "generate_configured_image", return_value=result) as generate:
            image = renderer.generate_background("fixture", render_metadata=metadata)
        self.assertEqual(image.size, (1080, 1080))
        self.assertEqual(metadata["image_model"], result.model)
        generate.assert_called_once()

    def test_arabic_font_loads_outside_repo_and_never_falls_back_to_latin(self):
        renderer = load_real_service("image_renderer")
        draw = __import__("PIL.ImageDraw", fromlist=["Draw"]).Draw(Image.new("RGB", (1080, 1080)))
        text = "نص اختباري غير قرآني"
        lines, font, _, _, _ = renderer.fit_text_to_zone(text, "missing.ttf", 900, 400, 68, draw, is_arabic=True)
        self.assertEqual(" ".join(lines), text)
        self.assertEqual(font.size, 68)
        self.assertTrue(Path(font.path).is_absolute())
        with patch.object(renderer, "ARABIC_FONT_PATH", "/missing-font.ttf"), self.assertRaises(ValueError):
            renderer.fit_text_to_zone(text, "missing.ttf", 900, 400, 68, draw, is_arabic=True)
