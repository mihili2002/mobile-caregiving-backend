
import requests

url = "http://127.0.0.1:5000/api/ai/check_profile/test_user"
print(f"Testing {url}")
try:
    resp = requests.get(url)
    print(f"Status: {resp.status_code}")
    print(resp.text)
except Exception as e:
    print(e)
