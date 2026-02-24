import requests
from bs4 import BeautifulSoup

def test_scraper():
    url = "https://sunnah.com/search?q=patience"
    headers = {"User-Agent": "Mozilla/5.0"}
    print(f"Fetching {url}...")
    r = requests.get(url, headers=headers)
    soup = BeautifulSoup(r.text, "html.parser")
    
    records = soup.select(".actualHadithContainer")
    print(f"Found {len(records)} records.")
    
    for i, rec in enumerate(records[:3]):
        text = rec.select_one(".english_hadith_full")
        ref = rec.select_one(".hadith_reference")
        print(f"\n--- Record {i+1} ---")
        print(f"Text: {text.get_text(' ', strip=True)[:100]}..." if text else "Text NOT FOUND")
        print(f"Ref: {ref.get_text(' ', strip=True)}" if ref else "Ref NOT FOUND")

if __name__ == "__main__":
    test_scraper()
