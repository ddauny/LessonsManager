from datetime import datetime, timedelta
import traceback
import google_calendar

try:
    creds = google_calendar.load_credentials()
    print('Loaded creds:', bool(creds))
    if not creds:
        raise SystemExit('No credentials found')
    start = datetime.utcnow() + timedelta(minutes=2)
    end = start + timedelta(minutes=30)
    print('Creating event from', start.isoformat(), 'to', end.isoformat())
    created = google_calendar.create_event('TEST EVENT FROM SCRIPT', start, end, description='Test event from container')
    print('Created event id:', created.get('id'))
except Exception as e:
    print('Exception while creating event:')
    traceback.print_exc()
