
import datetime

def test_minutes():
    # 10:29:01 - 10:30:00 = -59 seconds
    diff = datetime.timedelta(seconds=-59)
    # In Dart, Duration.inMinutes is:
    # return _duration ~/ Duration.microsecondsPerMinute;
    # where ~/ is integer division.
    
    # Integer division of -59,000,000 by 60,000,000 is 0.
    in_minutes = int(diff.total_seconds() / 60)
    print(f"Diff: {diff.total_seconds()}s, In Minutes: {in_minutes}")

test_minutes()
