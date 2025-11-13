#!/usr/bin/env python3
"""
Test script to verify Google Calendar sync functionality.
Run this after connecting Google Calendar to test the sync logic.
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import User, Lesson
from sync_calendar import parse_lesson_from_event, sync_user_calendar
from datetime import datetime


def test_parse_lesson_from_event():
    """Test event parsing logic."""
    print("\n=== Testing Event Parsing ===")
    
    # Test valid "Ripetizioni" format
    event1 = {
        'id': 'test123',
        'summary': 'Ripetizioni Mario Rossi',
        'start': {'dateTime': '2024-01-15T14:00:00Z'},
        'end': {'dateTime': '2024-01-15T15:00:00Z'},
        'description': 'Test lesson'
    }
    result1 = parse_lesson_from_event(event1)
    assert result1 is not None, "Should parse 'Ripetizioni' format"
    assert result1['student_name'] == 'Mario Rossi', f"Expected 'Mario Rossi', got {result1['student_name']}"
    print("✓ 'Ripetizioni Mario Rossi' parsed correctly")
    
    # Test valid "Lesson:" format
    event2 = {
        'id': 'test456',
        'summary': 'Lesson: Anna Verdi',
        'start': {'dateTime': '2024-01-15T16:00:00Z'},
        'end': {'dateTime': '2024-01-15T17:00:00Z'},
    }
    result2 = parse_lesson_from_event(event2)
    assert result2 is not None, "Should parse 'Lesson:' format"
    assert result2['student_name'] == 'Anna Verdi', f"Expected 'Anna Verdi', got {result2['student_name']}"
    print("✓ 'Lesson: Anna Verdi' parsed correctly")
    
    # Test invalid format (should be ignored)
    event3 = {
        'id': 'test789',
        'summary': 'Random Meeting',
        'start': {'dateTime': '2024-01-15T18:00:00Z'},
        'end': {'dateTime': '2024-01-15T19:00:00Z'},
    }
    result3 = parse_lesson_from_event(event3)
    assert result3 is None, "Should ignore events with wrong format"
    print("✓ 'Random Meeting' correctly ignored")
    
    # Test all-day event (should be ignored)
    event4 = {
        'id': 'test101',
        'summary': 'Ripetizioni All Day',
        'start': {'date': '2024-01-15'},
        'end': {'date': '2024-01-15'},
    }
    result4 = parse_lesson_from_event(event4)
    assert result4 is None, "Should ignore all-day events"
    print("✓ All-day events correctly ignored")
    
    print("✅ All parsing tests passed!\n")


def test_user_sync():
    """Test sync_user_calendar for first user (if exists)."""
    print("=== Testing User Calendar Sync ===")
    with app.app_context():
        user = User.query.first()
        if not user:
            print("⚠️  No users found in database. Create a user first.")
            return
        
        if not user.google_credentials:
            print(f"⚠️  User {user.email} has no Google Calendar connected.")
            print("   Connect Google Calendar first, then run this test.")
            return
        
        print(f"Testing sync for user: {user.email}")
        
        # Count lessons before sync
        before_count = Lesson.query.count()
        print(f"Lessons before sync: {before_count}")
        
        # Run sync
        try:
            synced = sync_user_calendar(user)
            print(f"Synced {synced} events")
            
            # Count lessons after sync
            after_count = Lesson.query.count()
            print(f"Lessons after sync: {after_count}")
            
            # Show recent synced lessons
            recent = Lesson.query.filter(Lesson.event_id.isnot(None)).order_by(Lesson.start_datetime.desc()).limit(5).all()
            if recent:
                print("\nRecent synced lessons:")
                for lesson in recent:
                    print(f"  - {lesson.student_name} @ {lesson.start_datetime} (event_id: {lesson.event_id})")
            
            print("✅ Sync completed successfully!\n")
        except Exception as e:
            print(f"❌ Sync failed: {e}")
            import traceback
            traceback.print_exc()


def test_webhook_channel():
    """Check if webhook channel is registered."""
    print("=== Testing Webhook Registration ===")
    with app.app_context():
        user = User.query.first()
        if not user:
            print("⚠️  No users found in database.")
            return
        
        if not user.google_channel:
            print(f"⚠️  User {user.email} has no webhook channel registered.")
            print("   Disconnect and reconnect Google Calendar to register webhook.")
            return
        
        import json
        channel_info = json.loads(user.google_channel)
        print(f"User: {user.email}")
        print(f"Channel ID: {channel_info.get('id')}")
        print(f"Resource ID: {channel_info.get('resourceId')}")
        
        expiration = channel_info.get('expiration')
        if expiration:
            expiration_dt = datetime.fromtimestamp(int(expiration) / 1000)
            print(f"Expires: {expiration_dt}")
            
            from datetime import timedelta
            time_left = expiration_dt - datetime.utcnow()
            print(f"Time remaining: {time_left.days} days, {time_left.seconds // 3600} hours")
        
        print("✅ Webhook channel is registered!\n")


if __name__ == '__main__':
    print("\n" + "="*50)
    print("Google Calendar Sync Test Suite")
    print("="*50)
    
    # Run all tests
    test_parse_lesson_from_event()
    test_user_sync()
    test_webhook_channel()
    
    print("="*50)
    print("Test suite completed!")
    print("="*50 + "\n")
