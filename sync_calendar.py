"""
Sync logic for Google Calendar webhooks.
When Google sends a notification, we fetch new/changed events and sync to DB.
"""
from models import User, Lesson, Student
from extensions import db
import google_calendar
from datetime import datetime
import re


def parse_lesson_from_event(event):
    """
    Parse Google Calendar event to extract lesson info.
    Expected title format: "Ripetizioni <student_name>" or "Lesson: <student_name>"
    Returns dict with student_name, start_datetime, end_datetime, or None if not a lesson event.
    """
    summary = event.get('summary', '')
    
    # Match patterns: "Ripetizioni <name>" or "Lesson: <name>"
    match = re.match(r'^(Ripetizioni|Lesson:?)\s+(.+)$', summary, re.IGNORECASE)
    if not match:
        return None
    
    student_name = match.group(2).strip()
    
    # Parse start/end times
    start = event.get('start', {})
    end = event.get('end', {})
    
    start_dt = None
    end_dt = None
    
    if 'dateTime' in start:
        start_dt = datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00'))
    elif 'date' in start:
        # all-day event: skip for now
        return None
    
    if 'dateTime' in end:
        end_dt = datetime.fromisoformat(end['dateTime'].replace('Z', '+00:00'))
    elif 'date' in end:
        return None
    
    if not start_dt or not end_dt:
        return None
    
    return {
        'student_name': student_name,
        'start_datetime': start_dt,
        'end_datetime': end_dt,
        'event_id': event.get('id'),
        'description': event.get('description', ''),
    }


def find_or_create_student(student_name):
    """
    Find student by name or create new one if not found.
    Tries to match by full name (first_name + last_name).
    Names are capitalized properly (first letter uppercase).
    """
    # Capitalize name properly (first letter of each word uppercase)
    student_name_formatted = ' '.join(word.capitalize() for word in student_name.strip().split())
    
    # Try to find existing student by full name (case-insensitive)
    students = Student.query.all()
    for student in students:
        full_name = f"{student.first_name} {student.last_name}".strip()
        if full_name.lower() == student_name_formatted.lower():
            return student
    
    # Student not found, create new one
    # Split name into first and last (assume last word is last name)
    parts = student_name_formatted.split()
    if len(parts) >= 2:
        first_name = ' '.join(parts[:-1])
        last_name = parts[-1]
    else:
        first_name = student_name_formatted
        last_name = ''
    
    new_student = Student(
        first_name=first_name,
        last_name=last_name,
        hourly_rate=0.0
    )
    db.session.add(new_student)
    db.session.flush()  # Get the ID without committing
    print(f"Created new student: {first_name} {last_name} (ID: {new_student.id})")
    return new_student


def sync_user_calendar(user: User):
    """
    Fetch recent calendar events for user and sync to Lesson table.
    Only creates/updates lessons from events titled "Ripetizioni <name>" or "Lesson: <name>".
    Also deletes lessons if their calendar event no longer exists.
    Associates lessons with existing students or creates new ones.
    """
    try:
        # Fetch events from last 30 days to next 90 days
        from datetime import timedelta
        time_min = datetime.utcnow() - timedelta(days=30)
        time_max = datetime.utcnow() + timedelta(days=90)
        
        events = google_calendar.list_events(user, time_min=time_min, time_max=time_max)
        
        # Build set of current event IDs in calendar
        calendar_event_ids = set()
        synced_count = 0
        
        for event in events:
            event_id = event.get('id')
            if event_id:
                calendar_event_ids.add(event_id)
            
            lesson_data = parse_lesson_from_event(event)
            if not lesson_data:
                continue
            
            student_name = lesson_data['student_name']
            start_datetime = lesson_data['start_datetime']
            end_datetime = lesson_data['end_datetime']
            
            # Capitalize student name properly (e.g., "samuele rossi" -> "Samuele Rossi")
            student_name_formatted = ' '.join(word.capitalize() for word in student_name.strip().split())
            
            # Check if lesson with this event_id already exists
            existing_by_event = Lesson.query.filter_by(event_id=event_id).first()
            
            if existing_by_event:
                # Update existing lesson with properly formatted name
                existing_by_event.student_name = student_name_formatted
                existing_by_event.start_datetime = start_datetime
                existing_by_event.end_datetime = end_datetime
                db.session.add(existing_by_event)
                synced_count += 1
                continue
            
            # Check if lesson with same name and datetime already exists (prevent duplicates on manual sync)
            existing_by_data = Lesson.query.filter_by(
                student_name=student_name_formatted,
                start_datetime=start_datetime
            ).first()
            
            if existing_by_data:
                # Just update the event_id to link them
                if not existing_by_data.event_id:
                    existing_by_data.event_id = event_id
                    db.session.add(existing_by_data)
                    print(f"Linked existing lesson {existing_by_data.id} with event {event_id}")
                synced_count += 1
                continue
            
            # Find or create student (with properly capitalized name)
            student = find_or_create_student(student_name_formatted)
            
            # Create new lesson with student's current hourly_rate
            lesson = Lesson(
                student_name=student_name_formatted,
                start_datetime=start_datetime,
                end_datetime=end_datetime,
                event_id=event_id,
                paid=False,
                already_paid=False,
                hourly_rate=student.hourly_rate if student.hourly_rate else None
            )
            db.session.add(lesson)
            synced_count += 1
        
        # Delete lessons whose event_id is no longer in calendar
        # (only delete lessons created from calendar, i.e., with event_id)
        existing_lessons = Lesson.query.filter(
            Lesson.event_id.isnot(None),
            Lesson.start_datetime >= time_min,
            Lesson.start_datetime <= time_max
        ).all()
        
        deleted_count = 0
        for lesson in existing_lessons:
            if lesson.event_id not in calendar_event_ids:
                print(f'Deleting lesson {lesson.id} (event {lesson.event_id} removed from calendar)')
                db.session.delete(lesson)
                deleted_count += 1
        
        db.session.commit()
        print(f"Synced {synced_count} lessons, deleted {deleted_count} for user {user.id}")
        return synced_count
    except Exception as e:
        print(f"Error syncing calendar for user {user.id}: {e}")
        import traceback
        traceback.print_exc()
        return 0
