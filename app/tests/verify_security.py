import requests

BASE_URL = "http://localhost:8000"
VALID_KEY = "your_admin_api_key_here" # This would need to match the env var

def test_unauthorized():
    print("Testing unauthorized access...")
    r = requests.get(f"{BASE_URL}/posts")
    print(f"Status: {r.status_code}")
    if r.status_code == 401:
        print("PASS: Unauthorized access blocked.")
    else:
        print("FAIL: Unauthorized access NOT blocked.")

def test_authorized():
    print("\nTesting authorized access...")
    # This test requires the server to be running and the key to match
    headers = {"X-API-Key": VALID_KEY}
    r = requests.get(f"{BASE_URL}/posts", headers=headers)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        print("PASS: Authorized access allowed.")
    else:
        print(f"FAIL: Authorized access returned {r.status_code}. Make sure your ADMIN_API_KEY env var matches.")

if __name__ == "__main__":
    test_unauthorized()
    # test_authorized() # Uncomment if server is running with VALID_KEY
