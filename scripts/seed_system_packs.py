import os
import sys
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import datetime
import pytz

# Add parent directory to path to import models and config if needed
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models import ContentSource, ContentItem

# Hardcoded production DB url from user env
DATABASE_URL = "postgresql://postgres:SRVGlFcxyhQVbJveWFmcxDzGVoeIjtgN@nozomi.proxy.rlwy.net:45252/railway"

# Data to seed
SYSTEM_PACKS = [
    {
        "name": "Starter Pack: General Reminders",
        "slug": "starter_general", # used for identification/internal mapping if needed, though name is main key
        "category": "starter",
        "description": "Short authentic reminders with clear references.",
        "entries": [
            {
                "resource_type": "hadith",
                "title": "Allah Looks at the Heart and Deeds",
                "text": "Indeed, Allah does not look at your appearance or wealth, but He looks at your hearts and your deeds.",
                "arabic_text": None,
                "meta": {
                    "source_name": "Sahih Muslim",
                    "reference_display": "Sahih Muslim 2564",
                    "hadith_collection": "Sahih Muslim",
                    "hadith_book": None,
                    "hadith_number": "2564",
                    "language": "en"
                },
                "topics": ["sincerity", "heart", "intentions", "deeds"]
            },
            {
                "resource_type": "hadith",
                "title": "Strength is Controlling Anger",
                "text": "The strong person is not the one who overcomes others by strength, but the one who controls himself while in anger.",
                "arabic_text": None,
                "meta": {
                    "source_name": "Sahih al-Bukhari",
                    "reference_display": "Sahih al-Bukhari 6114",
                    "hadith_collection": "Sahih al-Bukhari",
                    "hadith_book": None,
                    "hadith_number": "6114",
                    "language": "en"
                },
                "topics": ["anger", "self-control", "character", "strength"]
            },
            {
                "resource_type": "quran",
                "title": "Reliance Upon Allah",
                "text": "And whoever relies upon Allah – then He is sufficient for him.",
                "arabic_text": None,
                "meta": {
                    "source_name": "The Qur’an",
                    "reference_display": "Qur’an 65:3",
                    "quran_surah": "At-Talaq",
                    "quran_surah_number": 65,
                    "quran_verse_from": 3,
                    "quran_verse_to": 3,
                    "language": "en"
                },
                "topics": ["tawakkul", "trust", "reliance", "allah"]
            },
            {
                "resource_type": "hadith",
                "title": "The Most Beloved Deeds",
                "text": "The most beloved deeds to Allah are those that are consistent, even if small.",
                "arabic_text": None,
                "meta": {
                    "source_name": "Sahih al-Bukhari",
                    "reference_display": "Sahih al-Bukhari 6464",
                    "hadith_collection": "Sahih al-Bukhari",
                    "hadith_book": None,
                    "hadith_number": "6464",
                    "language": "en"
                },
                "topics": ["consistency", "deeds", "discipline", "worship"]
            },
            {
                "resource_type": "quran",
                "title": "Ease After Hardship",
                "text": "Indeed, with hardship comes ease.",
                "arabic_text": None,
                "meta": {
                    "source_name": "The Qur’an",
                    "reference_display": "Qur’an 94:6",
                    "quran_surah": "Ash-Sharh",
                    "quran_surah_number": 94,
                    "quran_verse_from": 6,
                    "quran_verse_to": 6,
                    "language": "en"
                },
                "topics": ["patience", "hope", "hardship", "ease"]
            }
        ]
    },
    {
        "name": "Starter Pack: Ramadan",
        "slug": "starter_ramadan",
        "category": "starter",
        "description": "Essential ahadeeth for the blessed month of Ramadan.",
        "entries": [
            {
                "resource_type": "hadith",
                "title": "Fasting Ramadan with Faith",
                "text": "Whoever fasts Ramadan with faith and seeking reward will have his past sins forgiven.",
                "arabic_text": None,
                "meta": {
                    "source_name": "Sahih al-Bukhari & Sahih Muslim",
                    "reference_display": "Sahih al-Bukhari 38; Sahih Muslim 760",
                    "hadith_collection": "Sahih al-Bukhari & Sahih Muslim",
                    "hadith_book": None,
                    "hadith_number": "38 / 760",
                    "language": "en"
                },
                "topics": ["ramadan", "fasting", "forgiveness", "reward"]
            },
            {
                "resource_type": "hadith",
                "title": "The Gates of Paradise in Ramadan",
                "text": "The gates of Paradise are opened in Ramadan, and the gates of Hell are closed.",
                "arabic_text": None,
                "meta": {
                    "source_name": "Sahih al-Bukhari",
                    "reference_display": "Sahih al-Bukhari 1899",
                    "hadith_collection": "Sahih al-Bukhari",
                    "hadith_book": None,
                    "hadith_number": "1899",
                    "language": "en"
                },
                "topics": ["ramadan", "paradise", "mercy", "fasting"]
            },
            {
                "resource_type": "hadith",
                "title": "The Prophet’s Generosity in Ramadan",
                "text": "The Messenger of Allah ﷺ was the most generous of people, and he was even more generous in Ramadan.",
                "arabic_text": None,
                "meta": {
                    "source_name": "Sahih al-Bukhari",
                    "reference_display": "Sahih al-Bukhari 6",
                    "hadith_collection": "Sahih al-Bukhari",
                    "hadith_book": None,
                    "hadith_number": "6",
                    "language": "en"
                },
                "topics": ["ramadan", "charity", "generosity", "character"]
            },
            {
                "resource_type": "hadith",
                "title": "Seek Laylat al-Qadr",
                "text": "Search for Laylat al-Qadr in the last ten nights of Ramadan.",
                "arabic_text": None,
                "meta": {
                    "source_name": "Sahih al-Bukhari",
                    "reference_display": "Sahih al-Bukhari 2020",
                    "hadith_collection": "Sahih al-Bukhari",
                    "hadith_book": None,
                    "hadith_number": "2020",
                    "language": "en"
                },
                "topics": ["ramadan", "laylatulqadr", "last ten nights", "worship"]
            },
            {
                "resource_type": "hadith",
                "title": "The Night of Qadr in the Last Nights",
                "text": '"Allah\'s Messenger (ﷺ) said, \'The Night of Qadr is in the last ten nights of the month (Ramadan), either on the first nine or in the last (remaining) seven nights (of Ramadan).\' Ibn Abbas added, \'Search for it on the twenty-fourth (of Ramadan).\'"',
                "arabic_text": "حَدَّثَنَا عَبْدُ اللَّهِ بْنُ أَبِي الأَسْوَدِ، حَدَّثَنَا عَاصِمٌ، عَنْ أَبِي مِجْلَزٍ، وَعِكْرِمَةَ، قَالَ ابْنُ عَبَّاسٍ ـ رضى الله عنهما ـ قَالَ قَالَ رَسُولُ اللَّهِ صلى الله عليه وسلم  \" هِيَ فِي الْعَشْرِ، هِيَ فِي تِسْعٍ يَمْضِينَ، أَوْ فِي سَبْعٍ يَبْقَيْنَ \" يَعْنِي لَيْلَةَ الْقَدْرِ. قَالَ عَبْدُ الْوَهَّابِ عَنْ أَيُّوبَ، وَعَنْ خَالِدٍ، عَنْ عِكْرِمَةَ عَنِ ابْنِ عَبَّاسٍ الْتَمِسُوهَا فِي أَرْبَعٍ وَعِشْرِينَ.",
                "meta": {
                    "source_name": "Sahih al-Bukhari",
                    "reference_display": "Sahih al-Bukhari 2022",
                    "hadith_collection": "Sahih al-Bukhari",
                    "hadith_book": None,
                    "hadith_number": "2022",
                    "language": "en"
                },
                "topics": ["ramadan", "laylatulqadr", "last ten nights", "qadr"]
            }
        ]
    }
]

def seed_database():
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()

    print("--- Starting System Packs Seed ---")
    
    for pack_data in SYSTEM_PACKS:
        # 1. UPSERT THE CONTENT SOURCE (PACK) - GLOBAL SCOPE (org_id = None)
        pack_name = pack_data["name"]
        pack = db.query(ContentSource).filter(
            ContentSource.name == pack_name,
            ContentSource.org_id == None
        ).first()

        if not pack:
            pack = ContentSource(
                org_id=None,
                name=pack_name,
                source_type="manual_library",
                category=pack_data["category"],
                description=pack_data["description"],
                config={"slug": pack_data["slug"]},
                enabled=True
            )
            db.add(pack)
            db.flush() # flush to get the ID
            print(f"Created system pack: '{pack_name}' (ID: {pack.id})")
        else:
            print(f"Found existing system pack: '{pack_name}' (ID: {pack.id})")
            # Update missing/changed metadata just in case
            pack.description = pack_data["description"]
            pack.category = pack_data["category"]

        # 2. UPSERT INDIVIDUAL ENTRIES
        for entry_data in pack_data["entries"]:
            # Match existing by source_id + title + reference_display
            existing_item = None
            # Need to search manually or via JSON queries if possible. Doing it python-side for perfect accuracy
            all_pack_items = db.query(ContentItem).filter(
                ContentItem.source_id == pack.id,
                ContentItem.org_id == None
            ).all()
            
            ref_target = entry_data["meta"]["reference_display"]
            
            for item in all_pack_items:
                # Check match criteria
                meta = item.meta or {}
                if item.title == entry_data["title"] and meta.get("reference_display") == ref_target:
                    existing_item = item
                    break
            
            if existing_item:
                print(f"  [UPDATE] '{entry_data['title']}'")
                # Update missing/changed fields
                existing_item.text = entry_data["text"]
                existing_item.arabic_text = entry_data["arabic_text"]
                existing_item.topics = entry_data["topics"]
                existing_item.item_type = entry_data["resource_type"]
                existing_meta = existing_item.meta or {}
                existing_meta.update(entry_data["meta"])
                # Also include approval_status in meta
                existing_meta["approval_status"] = "approved"
                existing_item.meta = existing_meta
                
                # Update topics_slugs based on app logici (basic lower/replace)
                slugs = [t.strip().lower().replace(" ", "_").replace("-", "") for t in entry_data["topics"]]
                existing_item.topics_slugs = slugs
            else:
                print(f"  [CREATE] '{entry_data['title']}'")
                # Need topics_slugs formatted
                slugs = [t.strip().lower().replace(" ", "_").replace("-", "") for t in entry_data["topics"]]
                
                entry_meta = entry_data["meta"]
                entry_meta["approval_status"] = "approved"
                
                new_item = ContentItem(
                    org_id=None,
                    source_id=pack.id,
                    owner_user_id=None,
                    item_type=entry_data["resource_type"],
                    title=entry_data["title"],
                    text=entry_data["text"],
                    arabic_text=entry_data["arabic_text"],
                    topics=entry_data["topics"],
                    topics_slugs=slugs,
                    meta=entry_meta,
                    tags=[]
                )
                db.add(new_item)
                
    try:
        db.commit()
        print("--- Seed Successful ---")
    except Exception as e:
        db.rollback()
        print(f"--- Seed Failed: {e} ---")
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
