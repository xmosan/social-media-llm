# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential.

from typing import Dict, Any, List, Optional
import logging
import re

logger = logging.getLogger(__name__)

# Static map of Surahs to ensure high-quality data even if the DB is missing fields.
SURAH_MAP = {
    1: {"en": "Al-Fatihah", "ar": "الفاتحة", "verses": 7, "type": "Meccan"},
    2: {"en": "Al-Baqarah", "ar": "البقرة", "verses": 286, "type": "Medinan"},
    3: {"en": "Ali 'Imran", "ar": "آل عمران", "verses": 200, "type": "Medinan"},
    4: {"en": "An-Nisa", "ar": "النساء", "verses": 176, "type": "Medinan"},
    5: {"en": "Al-Ma'idah", "ar": "المائدة", "verses": 120, "type": "Medinan"},
    6: {"en": "Al-An'am", "ar": "الأنعام", "verses": 165, "type": "Meccan"},
    7: {"en": "Al-A'raf", "ar": "الأعراف", "verses": 206, "type": "Meccan"},
    8: {"en": "Al-Anfal", "ar": "الأنفال", "verses": 75, "type": "Medinan"},
    9: {"en": "At-Tawbah", "ar": "التوبة", "verses": 129, "type": "Medinan"},
    10: {"en": "Yunus", "ar": "يونس", "verses": 109, "type": "Meccan"},
    11: {"en": "Hud", "ar": "هود", "verses": 123, "type": "Meccan"},
    12: {"en": "Yusuf", "ar": "يوسف", "verses": 111, "type": "Meccan"},
    13: {"en": "Ar-Ra'd", "ar": "الرعد", "verses": 43, "type": "Medinan"},
    14: {"en": "Ibrahim", "ar": "إبراهيم", "verses": 52, "type": "Meccan"},
    15: {"en": "Al-Hijr", "ar": "الحجر", "verses": 99, "type": "Meccan"},
    16: {"en": "An-Nahl", "ar": "النحل", "verses": 128, "type": "Meccan"},
    17: {"en": "Al-Isra", "ar": "الإسراء", "verses": 111, "type": "Meccan"},
    18: {"en": "Al-Kahf", "ar": "الكهف", "verses": 110, "type": "Meccan"},
    19: {"en": "Maryam", "ar": "مريم", "verses": 98, "type": "Meccan"},
    20: {"en": "Ta-Ha", "ar": "طة", "verses": 135, "type": "Meccan"},
    21: {"en": "Al-Anbiya", "ar": "الأنبياء", "verses": 112, "type": "Meccan"},
    22: {"en": "Al-Hajj", "ar": "الحج", "verses": 78, "type": "Medinan"},
    23: {"en": "Al-Mu'minun", "ar": "المؤمنون", "verses": 118, "type": "Meccan"},
    24: {"en": "An-Nur", "ar": "النور", "verses": 64, "type": "Medinan"},
    25: {"en": "Al-Furqan", "ar": "الفرقان", "verses": 77, "type": "Meccan"},
    26: {"en": "Ash-Shu'ara", "ar": "الشعراء", "verses": 227, "type": "Meccan"},
    27: {"en": "An-Naml", "ar": "النمل", "verses": 93, "type": "Meccan"},
    28: {"en": "Al-Qasas", "ar": "القصص", "verses": 88, "type": "Meccan"},
    29: {"en": "Al-'Ankabut", "ar": "العنكبوت", "verses": 69, "type": "Meccan"},
    30: {"en": "Ar-Rum", "ar": "الروم", "verses": 60, "type": "Meccan"},
    31: {"en": "Luqman", "ar": "لقمان", "verses": 34, "type": "Meccan"},
    32: {"en": "As-Sajdah", "ar": "السجدة", "verses": 30, "type": "Meccan"},
    33: {"en": "Al-Ahzab", "ar": "الأحزاب", "verses": 73, "type": "Medinan"},
    34: {"en": "Saba", "ar": "سبإ", "verses": 54, "type": "Meccan"},
    35: {"en": "Fatir", "ar": "فاطر", "verses": 45, "type": "Meccan"},
    36: {"en": "Ya-Sin", "ar": "يس", "verses": 83, "type": "Meccan"},
    37: {"en": "As-Saffat", "ar": "الصافات", "verses": 182, "type": "Meccan"},
    38: {"en": "Sad", "ar": "ص", "verses": 88, "type": "Meccan"},
    39: {"en": "Az-Zumar", "ar": "الزمر", "verses": 75, "type": "Meccan"},
    40: {"en": "Ghafir", "ar": "غافر", "verses": 85, "type": "Meccan"},
    41: {"en": "Fussilat", "ar": "فصلت", "verses": 54, "type": "Meccan"},
    42: {"en": "Ash-Shura", "ar": "الشورى", "verses": 53, "type": "Meccan"},
    43: {"en": "Az-Zukhruf", "ar": "الزخرف", "verses": 89, "type": "Meccan"},
    44: {"en": "Ad-Dukhan", "ar": "الدخان", "verses": 59, "type": "Meccan"},
    45: {"en": "Al-Jathiyah", "ar": "الجاثية", "verses": 37, "type": "Meccan"},
    46: {"en": "Al-Ahqaf", "ar": "الأحقاف", "verses": 35, "type": "Meccan"},
    47: {"en": "Muhammad", "ar": "محمد", "verses": 38, "type": "Medinan"},
    48: {"en": "Al-Fath", "ar": "الفتح", "verses": 29, "type": "Medinan"},
    49: {"en": "Al-Hujurat", "ar": "الحجرات", "verses": 18, "type": "Medinan"},
    50: {"en": "Qaf", "ar": "ق", "verses": 45, "type": "Meccan"},
    51: {"en": "Adh-Dhariyat", "ar": "الذاريات", "verses": 60, "type": "Meccan"},
    52: {"en": "At-Tur", "ar": "الطور", "verses": 49, "type": "Meccan"},
    53: {"en": "An-Najm", "ar": "النجم", "verses": 62, "type": "Meccan"},
    54: {"en": "Al-Qamar", "ar": "القمر", "verses": 55, "type": "Meccan"},
    55: {"en": "Ar-Rahman", "ar": "الرحمن", "verses": 78, "type": "Medinan"},
    56: {"en": "Al-Waqi'ah", "ar": "الواقعة", "verses": 96, "type": "Meccan"},
    57: {"en": "Al-Hadid", "ar": "الحديد", "verses": 29, "type": "Medinan"},
    58: {"en": "Al-Mujadila", "ar": "المجادلة", "verses": 22, "type": "Medinan"},
    59: {"en": "Al-Hashr", "ar": "الحشر", "verses": 24, "type": "Medinan"},
    60: {"en": "Al-Mumtahanah", "ar": "الممتحنة", "verses": 13, "type": "Medinan"},
    61: {"en": "As-Saff", "ar": "الصف", "verses": 14, "type": "Medinan"},
    62: {"en": "Al-Jumu'ah", "ar": "الجمعة", "verses": 11, "type": "Medinan"},
    63: {"en": "Al-Munafiqun", "ar": "المنافقون", "verses": 11, "type": "Medinan"},
    64: {"en": "At-Taghabun", "ar": "التغابن", "verses": 18, "type": "Medinan"},
    65: {"en": "At-Talaq", "ar": "الطلاق", "verses": 12, "type": "Medinan"},
    66: {"en": "At-Tahrim", "ar": "التحريم", "verses": 12, "type": "Medinan"},
    67: {"en": "Al-Mulk", "ar": "الملك", "verses": 30, "type": "Meccan"},
    68: {"en": "Al-Qalam", "ar": "القلم", "verses": 52, "type": "Meccan"},
    69: {"en": "Al-Haqqah", "ar": "الحاقة", "verses": 52, "type": "Meccan"},
    70: {"en": "Al-Ma'arij", "ar": "المعارج", "verses": 44, "type": "Meccan"},
    71: {"en": "Nuh", "ar": "نوح", "verses": 28, "type": "Meccan"},
    72: {"en": "Al-Jinn", "ar": "الجن", "verses": 28, "type": "Meccan"},
    73: {"en": "Al-Muzzammil", "ar": "المزمل", "verses": 20, "type": "Meccan"},
    74: {"en": "Al-Muddaththir", "ar": "المدثر", "verses": 56, "type": "Meccan"},
    75: {"en": "Al-Qiyamah", "ar": "القيامة", "verses": 40, "type": "Meccan"},
    76: {"en": "Al-Insan", "ar": "الإنسان", "verses": 31, "type": "Medinan"},
    77: {"en": "Al-Mursalat", "ar": "المرسلات", "verses": 50, "type": "Meccan"},
    78: {"en": "An-Naba", "ar": "النبإ", "verses": 40, "type": "Meccan"},
    79: {"en": "An-Nazi'at", "ar": "النازعات", "verses": 46, "type": "Meccan"},
    80: {"en": "'Abasa", "ar": "عبس", "verses": 42, "type": "Meccan"},
    81: {"en": "At-Takwir", "ar": "التكوير", "verses": 29, "type": "Meccan"},
    82: {"en": "Al-Infitar", "ar": "الانفطار", "verses": 19, "type": "Meccan"},
    83: {"en": "Al-Mutaffifin", "ar": "المطففين", "verses": 36, "type": "Meccan"},
    84: {"en": "Al-Inshiqaq", "ar": "الانشقاق", "verses": 25, "type": "Meccan"},
    85: {"en": "Al-Buruj", "ar": "البروج", "verses": 22, "type": "Meccan"},
    86: {"en": "At-Tariq", "ar": "الطارق", "verses": 17, "type": "Meccan"},
    87: {"en": "Al-A'la", "ar": "الأعلى", "verses": 19, "type": "Meccan"},
    88: {"en": "Al-Ghashiyah", "ar": "الغاشية", "verses": 26, "type": "Meccan"},
    89: {"en": "Al-Fajr", "ar": "الفجر", "verses": 30, "type": "Meccan"},
    90: {"en": "Al-Balad", "ar": "البلد", "verses": 20, "type": "Meccan"},
    91: {"en": "Ash-Shams", "ar": "الشمس", "verses": 15, "type": "Meccan"},
    92: {"en": "Al-Layl", "ar": "الليل", "verses": 21, "type": "Meccan"},
    93: {"en": "Ad-Duha", "ar": "الضحى", "verses": 11, "type": "Meccan"},
    94: {"en": "Ash-Sharh", "ar": "الشرح", "verses": 8, "type": "Meccan"},
    95: {"en": "At-Tin", "ar": "التين", "verses": 8, "type": "Meccan"},
    96: {"en": "Al-'Alaq", "ar": "العلق", "verses": 19, "type": "Meccan"},
    97: {"en": "Al-Qadr", "ar": "القدر", "verses": 5, "type": "Meccan"},
    98: {"en": "Al-Bayyinah", "ar": "البينة", "verses": 8, "type": "Medinan"},
    99: {"en": "Az-Zalzalah", "ar": "الزلزلة", "verses": 8, "type": "Medinan"},
    100: {"en": "Al-'Adiyat", "ar": "العاديات", "verses": 11, "type": "Meccan"},
    101: {"en": "Al-Qari'ah", "ar": "القارعة", "verses": 11, "type": "Meccan"},
    102: {"en": "At-Takathur", "ar": "التكاثر", "verses": 8, "type": "Meccan"},
    103: {"en": "Al-'Asr", "ar": "العصر", "verses": 3, "type": "Meccan"},
    104: {"en": "Al-Humazah", "ar": "الهمزة", "verses": 9, "type": "Meccan"},
    105: {"en": "Al-Fil", "ar": "الفيل", "verses": 5, "type": "Meccan"},
    106: {"en": "Quraysh", "ar": "قريش", "verses": 4, "type": "Meccan"},
    107: {"en": "Al-Ma'un", "ar": "الماعون", "verses": 7, "type": "Meccan"},
    108: {"en": "Al-Kawthar", "ar": "الكوثر", "verses": 3, "type": "Meccan"},
    109: {"en": "Al-Kafirun", "ar": "الكافرون", "verses": 6, "type": "Meccan"},
    110: {"en": "An-Nasr", "ar": "النصر", "verses": 3, "type": "Medinan"},
    111: {"en": "Al-Masad", "ar": "المسد", "verses": 5, "type": "Meccan"},
    112: {"en": "Al-Ikhlas", "ar": "الإخلاص", "verses": 4, "type": "Meccan"},
    113: {"en": "Al-Falaq", "ar": "الفلق", "verses": 5, "type": "Meccan"},
    114: {"en": "An-Nas", "ar": "الناس", "verses": 6, "type": "Meccan"},
}

def normalize_quran_verse(item: Any) -> Dict[str, Any]:
    """
    Transforms a database ContentItem or generic dictionary into a 
    standardized Quran verse payload.
    Ensures 'No UNDEFINED', 'No missing titles', etc.
    """
    if not item:
        return {}

    # 1. Handle different input types (SQLAlchemy model vs Dict)
    if hasattr(item, "__table__"):
        # It's an ORM object
        item_id = item.id
        raw_meta = item.meta or {}
        raw_title = item.title or ""
        arabic_text = item.arabic_text or ""
        translation_text = item.text or ""
        topics = item.topics or []
    else:
        # It's already a dict
        item_id = item.get("id")
        raw_meta = item.get("meta") or {}
        raw_title = item.get("title") or ""
        arabic_text = item.get("arabic") or item.get("arabic_text") or ""
        translation_text = item.get("text") or item.get("translation_text") or ""
        topics = item.get("topics") or []

    # 2. Extract Surah/Ayah numbers with robust fallback
    surah_num = raw_meta.get("surah_number") or raw_meta.get("surah")
    ayah_num = raw_meta.get("verse_number") or raw_meta.get("ayah")

    if not surah_num or not ayah_num:
        # 1. Try "Surah X, Verse Y" format
        m = re.search(r"Surah\s+(\d+)[\s,]+Verse\s+(\d+)", raw_title, re.IGNORECASE)
        if m:
            surah_num = int(m.group(1))
            ayah_num = int(m.group(2))
        else:
            # 2. Try any "X:Y" or "X Y" format
            m = re.search(r"(\d+)[:,\s]+(\d+)", raw_title)
            if m:
                surah_num = int(m.group(1))
                ayah_num = int(m.group(2))

    # Strict fallback: DO NOT default to 1:1 if we found nothing. 
    # Use 0:0 to signify a parsing failure so we don't report incorrect references.
    surah_num = int(surah_num) if surah_num else 0
    ayah_num = int(ayah_num) if ayah_num else 0

    # 3. Enrich Surah names from map
    surah_info = SURAH_MAP.get(surah_num, {"en": "Unknown Surah", "ar": ""})
    
    # 3.5 CLEANING: Strip the Basmala prefix if present (except for Al-Fatihah 1:1)
    # Standard Basmala string in many datasets: بِسْمِ اللَّهِ الرَّحْمَنِ الرَّحِيمِ
    basmala = "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ"
    if surah_num != 1 and arabic_text.startswith(basmala):
        arabic_text = arabic_text[len(basmala):].strip()
    
    # 4. Final Construction
    verse_key = f"{surah_num}:{ayah_num}"
    reference = f"Qur'an {verse_key}"
    
    trans_id = raw_meta.get("translation_id", "131")
    translator = "Sahih International" if str(trans_id) == "131" else f"Translator {trans_id}"

    normalized = {
        "id": item_id,
        "type": "quran_verse",
        "surah_number": surah_num,
        "surah_name_en": surah_info["en"],
        "surah_name_ar": surah_info["ar"],
        "ayah_number": ayah_num,
        "verse_key": verse_key,
        "reference": reference,
        "arabic_text": arabic_text,
        "translation_text": translation_text,
        "translator": translator,
        "topics": topics
    }
    
    if not normalized["translation_text"]:
        normalized["translation_text"] = "[Translation not available]"
        logger.warning(f"⚠️ Quran normalization: missing translation for {reference}")

    return normalized
