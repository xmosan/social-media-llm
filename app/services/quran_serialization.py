# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential.

from typing import Dict, Any, List, Optional
import logging
import re

logger = logging.getLogger(__name__)

# Static map of Surahs to ensure high-quality data even if the DB is missing fields.
SURAH_MAP = {
    1: {"en": "Al-Fatihah", "ar": "الفاتحة"},
    2: {"en": "Al-Baqarah", "ar": "البقرة"},
    3: {"en": "Ali 'Imran", "ar": "آل عمران"},
    4: {"en": "An-Nisa", "ar": "النساء"},
    5: {"en": "Al-Ma'idah", "ar": "المائدة"},
    6: {"en": "Al-An'am", "ar": "الأنعام"},
    7: {"en": "Al-A'raf", "ar": "الأعراف"},
    8: {"en": "Al-Anfal", "ar": "الأنفال"},
    9: {"en": "At-Tawbah", "ar": "التوبة"},
    10: {"en": "Yunus", "ar": "يونس"},
    11: {"en": "Hud", "ar": "هود"},
    12: {"en": "Yusuf", "ar": "يوسف"},
    13: {"en": "Ar-Ra'd", "ar": "الرعد"},
    14: {"en": "Ibrahim", "ar": "إبراهيم"},
    15: {"en": "Al-Hijr", "ar": "الحجر"},
    16: {"en": "An-Nahl", "ar": "النحل"},
    17: {"en": "Al-Isra", "ar": "الإسراء"},
    18: {"en": "Al-Kahf", "ar": "الكهف"},
    19: {"en": "Maryam", "ar": "مريم"},
    20: {"en": "Ta-Ha", "ar": "طه"},
    21: {"en": "Al-Anbiya", "ar": "الأنبياء"},
    22: {"en": "Al-Hajj", "ar": "الحج"},
    23: {"en": "Al-Mu'minun", "ar": "المؤمنون"},
    24: {"en": "An-Nur", "ar": "النور"},
    25: {"en": "Al-Furqan", "ar": "الفرقان"},
    26: {"en": "Ash-Shu'ara", "ar": "الشعراء"},
    27: {"en": "An-Naml", "ar": "النمل"},
    28: {"en": "Al-Qasas", "ar": "القصص"},
    29: {"en": "Al-'Ankabut", "ar": "العنكبوت"},
    30: {"en": "Ar-Rum", "ar": "الروم"},
    31: {"en": "Luqman", "ar": "لقمان"},
    32: {"en": "As-Sajdah", "ar": "السجدة"},
    33: {"en": "Al-Ahzab", "ar": "الأحزاب"},
    34: {"en": "Saba", "ar": "سبأ"},
    35: {"en": "Fatir", "ar": "فاطر"},
    36: {"en": "Ya-Sin", "ar": "يس"},
    37: {"en": "As-Saffat", "ar": "الصافات"},
    38: {"en": "Sad", "ar": "ص"},
    39: {"en": "Az-Zumar", "ar": "الزمر"},
    40: {"en": "Ghafir", "ar": "غافر"},
    41: {"en": "Fussilat", "ar": "فصلت"},
    42: {"en": "Ash-Shura", "ar": "الشورى"},
    43: {"en": "Az-Zukhruf", "ar": "الزخرف"},
    44: {"en": "Ad-Dukhan", "ar": "الدخان"},
    45: {"en": "Al-Jathiyah", "ar": "الجاثية"},
    46: {"en": "Al-Ahqaf", "ar": "الأحقاف"},
    47: {"en": "Muhammad", "ar": "محمد"},
    48: {"en": "Al-Fath", "ar": "الفتح"},
    49: {"en": "Al-Hujurat", "ar": "الحجرات"},
    50: {"en": "Qaf", "ar": "ق"},
    51: {"en": "Adh-Dhariyat", "ar": "الذاريات"},
    52: {"en": "At-Tur", "ar": "الطور"},
    53: {"en": "An-Najm", "ar": "النجم"},
    54: {"en": "Al-Qamar", "ar": "القمر"},
    55: {"en": "Ar-Rahman", "ar": "الرحمن"},
    56: {"en": "Al-Waqi'ah", "ar": "الواقعة"},
    57: {"en": "Al-Hadid", "ar": "الحديد"},
    58: {"en": "Al-Mujadila", "ar": "المجادلة"},
    59: {"en": "Al-Hashr", "ar": "الحشر"},
    60: {"en": "Al-Mumtahanah", "ar": "الممتحنة"},
    61: {"en": "As-Saff", "ar": "الصف"},
    62: {"en": "Al-Jumu'ah", "ar": "الجمعة"},
    63: {"en": "Al-Munafiqun", "ar": "المنافقون"},
    64: {"en": "At-Taghabun", "ar": "التغابن"},
    65: {"en": "At-Talaq", "ar": "الطلاق"},
    66: {"en": "At-Tahrim", "ar": "التحريم"},
    67: {"en": "Al-Mulk", "ar": "الملك"},
    68: {"en": "Al-Qalam", "ar": "القلم"},
    69: {"en": "Al-Haqqah", "ar": "الحاقة"},
    70: {"en": "Al-Ma'arij", "ar": "المعارج"},
    71: {"en": "Nuh", "ar": "نوح"},
    72: {"en": "Al-Jinn", "ar": "الجن"},
    73: {"en": "Al-Muzzammil", "ar": "المزمل"},
    74: {"en": "Al-Muddaththir", "ar": "المدثر"},
    75: {"en": "Al-Qiyamah", "ar": "القيامة"},
    76: {"en": "Al-Insan", "ar": "الإنسان"},
    77: {"en": "Al-Mursalat", "ar": "المرسلات"},
    78: {"en": "An-Naba", "ar": "النبأ"},
    79: {"en": "An-Nazi'at", "ar": "النازعات"},
    80: {"en": "'Abasa", "ar": "عبس"},
    81: {"en": "At-Takwir", "ar": "التكوير"},
    82: {"en": "Al-Infitar", "ar": "الانفطار"},
    83: {"en": "Al-Mutaffifin", "ar": "المطففين"},
    84: {"en": "Al-Inshiqaq", "ar": "الانشقاق"},
    85: {"en": "Al-Buruj", "ar": "البروج"},
    86: {"en": "At-Tariq", "ar": "الطارق"},
    87: {"en": "Al-A'la", "ar": "الأعلى"},
    88: {"en": "Al-Ghashiyah", "ar": "الغاشية"},
    89: {"en": "Al-Fajr", "ar": "الفجر"},
    90: {"en": "Al-Balad", "ar": "البلد"},
    91: {"en": "Ash-Shams", "ar": "الشمس"},
    92: {"en": "Al-Layl", "ar": "الليل"},
    93: {"en": "Ad-Duha", "ar": "الضحى"},
    94: {"en": "Ash-Sharh", "ar": "الشرح"},
    95: {"en": "At-Tin", "ar": "التين"},
    96: {"en": "Al-'Alaq", "ar": "العلق"},
    97: {"en": "Al-Qadr", "ar": "القدر"},
    98: {"en": "Al-Bayyinah", "ar": "البينة"},
    99: {"en": "Az-Zalzalah", "ar": "الزلزلة"},
    100: {"en": "Al-'Adiyat", "ar": "العاديات"},
    101: {"en": "Al-Qari'ah", "ar": "القارعة"},
    102: {"en": "At-Takathur", "ar": "التكاثر"},
    103: {"en": "Al-'Asr", "ar": "العصر"},
    104: {"en": "Al-Humazah", "ar": "الهمزة"},
    105: {"en": "Al-Fil", "ar": "الفيل"},
    106: {"en": "Quraysh", "ar": "قريش"},
    107: {"en": "Al-Ma'un", "ar": "الماعون"},
    108: {"en": "Al-Kawthar", "ar": "الكوثر"},
    109: {"en": "Al-Kafirun", "ar": "الكافرون"},
    110: {"en": "An-Nasr", "ar": "النصر"},
    111: {"en": "Al-Masad", "ar": "المسد"},
    112: {"en": "Al-Ikhlas", "ar": "الإخلاص"},
    113: {"en": "Al-Falaq", "ar": "الفلق"},
    114: {"en": "An-Nas", "ar": "الناس"}
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
        match = re.search(r"(\d+)[:,\s]+(\d+)", raw_title)
        if match:
            if not surah_num: surah_num = int(match.group(1))
            if not ayah_num: ayah_num = int(match.group(2))

    surah_num = int(surah_num) if surah_num else 1
    ayah_num = int(ayah_num) if ayah_num else 1

    # 3. Enrich Surah names from map
    surah_info = SURAH_MAP.get(surah_num, {"en": "Unknown Surah", "ar": ""})
    
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
