"""Synthetic source fixtures; exact text and offsets must survive decoration."""
import io
from copy import deepcopy
import unittest
from PIL import Image
from app.services.brand_kit import normalize_brand
from app.services.quran_ornaments import card_ornaments
from app.services.card_typography import layout_card, plan_sequence, paint_card_text, check_encoded_contrast, _ink_mask


CARD = {"eyebrow": "Qur'an 2:153", "arabic_text": "نص اختباري غير قرآني", "headline": "Synthetic source, not scripture."}


def segments(card, brand):
    return [{"role": "source_arabic", "text": card["arabic_text"], "quran_ornaments": card_ornaments(card, brand)},
            {"role": "source_translation", "text": card["headline"]},
            {"role": "reference", "text": card["eyebrow"]}]


class QuranOrnamentTests(unittest.TestCase):
    def test_settings_are_strict_and_legacy_off_snapshots_do_not_change(self):
        default = normalize_brand()
        self.assertEqual(normalize_brand({"quran_ornaments": {"brackets": False, "verse_number": False}}), default)
        for bad in (None, [], {"verse_number": 12}, {"brackets": "false"}, {"text": "override"}):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                normalize_brand({"quran_ornaments": bad})

    def test_markers_use_the_reference_and_never_rewrite_the_card(self):
        before = deepcopy(CARD)
        kit = normalize_brand({"quran_ornaments": {"brackets": True, "verse_number": True}})
        for reference, number in (("Qur'an 94:6", 6), ("Qur'an 14:34", 34), ("Qur'an 2:282", 282)):
            card = {**CARD, "eyebrow": reference}
            self.assertEqual(card_ornaments(card, kit)["verse_number"], number)
        self.assertEqual(CARD, before)
        with self.assertRaises(ValueError): card_ornaments({**CARD, "eyebrow": "Qur'an 114:7"}, kit)
        with self.assertRaises(ValueError): card_ornaments({**CARD, "source_complete": False}, kit)
        self.assertIsNone(card_ornaments({**CARD, "eyebrow": "Sahih al-Bukhari 153", "was_excerpted": False}, kit))
        self.assertEqual(card_ornaments({**CARD, "arabic_text": "﴿"+CARD["arabic_text"]+"﴾ ۝١٥٣"}, kit), {"opening": False, "closing": False, "verse_number": None})

    def test_all_four_choices_fit_and_contrast_checks_include_the_ornaments(self):
        before = deepcopy(CARD)
        for brackets in (False, True):
            for number in (False, True):
                kit = normalize_brand({"quran_ornaments": {"brackets": brackets, "verse_number": number}})
                size, blocks = layout_card(segments(CARD, kit), brand_kit=kit)
                ar = next(b for b in blocks if b["role"] == "source_arabic")
                runs = [r for line in ar["lines"] for r in line.get("runs", [])]
                self.assertEqual(sum(r["text"] == "\ufd3f" for r in runs), int(brackets))
                self.assertEqual(sum(r["text"].startswith("\u06dd") for r in runs), int(number))
                mask = _ink_mask(size, ar, "Left")
                x0,y0,x1,y1=mask.getbbox(); left,top,right,bottom=ar["bounds"]
                self.assertTrue(left <= x0 < x1 <= right and top <= y0 < y1 <= bottom)
                background=Image.new("RGB",size,(246,244,236)); quality={}
                painted=paint_card_text(background,blocks,quality=quality)
                encoded=io.BytesIO();painted.save(encoded,format="JPEG",quality=95)
                check_encoded_contrast(Image.open(io.BytesIO(encoded.getvalue())),background,blocks,quality)
                self.assertGreaterEqual(quality["encoded_minimum_contrast"],4.5)
        self.assertEqual(CARD,before)

    def test_long_sequences_mark_only_the_true_verse_boundaries(self):
        card = {**CARD, "arabic_text": (CARD["arabic_text"] + " ") * 46}
        kit = normalize_brand({"quran_ornaments": {"brackets": True, "verse_number": True}})
        before=deepcopy(card)
        for fmt in ("feed_4_5", "story_9_16"):
            pages=plan_sequence(segments(card,kit),brand_kit=kit,post_format=fmt)
            ar=[s for p in pages for s in p["segments"] if s["role"]=="source_arabic"]
            self.assertGreater(len(ar),1)
            self.assertEqual("".join(s["text"] for s in ar),card["arabic_text"])
            self.assertTrue(ar[0]["quran_ornaments"]["opening"])
            self.assertTrue(ar[-1]["quran_ornaments"]["closing"])
            self.assertEqual(ar[-1]["quran_ornaments"]["verse_number"],153)
            self.assertFalse(any(s["quran_ornaments"]["opening"] for s in ar[1:]))
            self.assertFalse(any(s["quran_ornaments"]["closing"] or s["quran_ornaments"]["verse_number"] for s in ar[:-1]))
            for page in pages:
                size,blocks=layout_card(page["segments"],brand_kit=kit,post_format=fmt)
                for block in blocks:
                    x0,y0,x1,y1=_ink_mask(size,block,"Left").getbbox()
                    left,top,right,bottom=block["bounds"]
                    self.assertTrue(left <= x0 < x1 <= right and top <= y0 < y1 <= bottom)
        self.assertEqual(card,before)
