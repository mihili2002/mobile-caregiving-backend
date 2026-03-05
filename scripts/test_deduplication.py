import requests
import json

def test_suggestions():
    uid = "2UzD3jw7LXXQ7rVetKpsR7iB7vg2"
    url = f"http://127.0.0.1:8000/get_daily_suggestions/{uid}"
    
    print(f"Testing suggestions for UID: {uid}")
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            common = data.get('common', [])
            
            names = [t['task_name'].lower() for t in common]
            duplicates = set([x for x in names if names.count(x) > 1])
            
            print(f"Received {len(common)} common tasks.")
            if duplicates:
                print(f"❌ FAIL: Found duplicate task names: {duplicates}")
            else:
                print("✅ PASS: No duplicate task names found.")
                for t in common:
                    print(f"  - {t['task_name']} ({t['default_time']})")
        else:
            print(f"❌ ERROR: Backend returned status {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"❌ CONNECTION ERROR: {e}")

def test_get_schedule():
    uid = "2UzD3jw7LXXQ7rVetKpsR7iB7vg2"
    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d")
    url = "http://127.0.0.1:8000/api/schedule/get_schedule"
    
    print(f"\nTesting get_schedule for UID: {uid}, Date: {date_str}")
    try:
        response = requests.post(url, json={"uid": uid, "date": date_str})
        if response.status_code == 200:
            data = response.json()
            tasks = data.get('tasks', [])
            
            names_and_times = [(t['task_name'].lower(), t['time']) for t in tasks]
            duplicates = set([x for x in names_and_times if names_and_times.count(x) > 1])
            
            print(f"Received {len(tasks)} tasks.")
            if duplicates:
                print(f"❌ FAIL: Found duplicate tasks: {duplicates}")
            else:
                print("✅ PASS: No duplicate tasks found in schedule.")
                for t in tasks:
                    print(f"  - {t['task_name']} ({t['time']})")
        else:
            print(f"❌ ERROR: Backend returned status {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"❌ CONNECTION ERROR: {e}")

if __name__ == "__main__":
    test_suggestions()
    test_get_schedule()
