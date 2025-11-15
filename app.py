from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, current_user, login_required
from datetime import datetime, timedelta
import os
import secrets
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from forms import LoginForm, RegisterForm, LessonForm

# Application setup
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET') or secrets.token_hex(32)
# Use absolute path for SQLite database
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(basedir, "instance", "ripetizioni.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# FinTrack integration settings
app.config['FINTRACK_URL'] = os.environ.get('FINTRACK_URL', 'http://localhost:3000')
app.config['FINTRACK_TOKEN'] = os.environ.get('FINTRACK_TOKEN', '')
app.config['FINTRACK_ACCOUNT_ID'] = os.environ.get('FINTRACK_ACCOUNT_ID', '')  # accountId per le transazioni

from extensions import db
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

from models import User, Lesson, Student, Topic, StudentPhoto
from forms import StudentForm, TopicForm
from werkzeug.utils import secure_filename

# Try to import google_calendar module
try:
    import google_calendar
    GOOGLE_CALENDAR_ENABLED = True
except Exception as e:
    print(f'Warning: Google Calendar module not available: {e}')
    google_calendar = None
    GOOGLE_CALENDAR_ENABLED = False

UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


# Ensure DB schema for development: create tables and add new columns if missing.
def ensure_schema():
    with app.app_context():
        try:
            # create tables if missing
            db.create_all()
        except Exception as e:
            print('create_all error:', e)

        # For SQLite, use the sqlite3 module to add the column if missing (ensures the ALTER runs)
        try:
            import sqlite3
            basedir = os.path.abspath(os.path.dirname(__file__))
            db_path = os.path.join(basedir, 'instance', 'ripetizioni.db')
            if os.path.exists(db_path):
                con = sqlite3.connect(db_path)
                cur = con.cursor()
                
                # Check lesson table
                cur.execute("PRAGMA table_info('lesson')")
                rows = cur.fetchall()
                cols = [r[1] for r in rows]
                if 'paid_at' not in cols:
                    print('Adding missing column lesson.paid_at (sqlite3)')
                    cur.execute("ALTER TABLE lesson ADD COLUMN paid_at DATETIME")
                    con.commit()
                
                # Check student table
                cur.execute("PRAGMA table_info('student')")
                rows = cur.fetchall()
                cols = [r[1] for r in rows]
                if 'payment_method' not in cols:
                    print('Adding missing column student.payment_method (sqlite3)')
                    cur.execute("ALTER TABLE student ADD COLUMN payment_method VARCHAR(64)")
                    con.commit()
                if 'hourly_rate' not in cols:
                    print('Adding missing column student.hourly_rate (sqlite3)')
                    cur.execute("ALTER TABLE student ADD COLUMN hourly_rate FLOAT")
                    con.commit()
                
                # Check lesson table for event_id
                cur.execute("PRAGMA table_info('lesson')")
                rows = cur.fetchall()
                cols = [r[1] for r in rows]
                if 'event_id' not in cols:
                    print('Adding missing column lesson.event_id (sqlite3)')
                    cur.execute("ALTER TABLE lesson ADD COLUMN event_id VARCHAR(255)")
                    con.commit()
                if 'already_paid' not in cols:
                    print('Adding missing column lesson.already_paid (sqlite3)')
                    cur.execute("ALTER TABLE lesson ADD COLUMN already_paid BOOLEAN DEFAULT 0")
                    con.commit()
                if 'hourly_rate' not in cols:
                    print('Adding missing column lesson.hourly_rate (sqlite3)')
                    cur.execute("ALTER TABLE lesson ADD COLUMN hourly_rate FLOAT")
                    con.commit()
                
                # Check user table for google_credentials
                cur.execute("PRAGMA table_info('user')")
                rows = cur.fetchall()
                cols = [r[1] for r in rows]
                if 'google_credentials' not in cols:
                    print('Adding missing column user.google_credentials (sqlite3)')
                    cur.execute("ALTER TABLE user ADD COLUMN google_credentials TEXT")
                    con.commit()
                if 'google_channel' not in cols:
                    print('Adding missing column user.google_channel (sqlite3)')
                    cur.execute("ALTER TABLE user ADD COLUMN google_channel TEXT")
                    con.commit()
                
                cur.close()
                con.close()
        except Exception as e:
            print('sqlite3 schema alter error:', e)


# Run schema ensure immediately so views don't hit missing columns
ensure_schema()


def send_to_fintrack(amount: float, notes: str, payment_method: str = None, transaction_date: datetime = None) -> bool:
    """
    Send a transaction to FinTrack when a lesson is marked as paid.
    Returns True if successful, False otherwise.
    
    Args:
        amount: The amount to send
        notes: Transaction notes
        payment_method: Optional payment method (cash/paypal/bank)
        transaction_date: The date when the transaction was marked as paid (uses current date if not provided)
    """
    # Skip if FinTrack is not configured
    if not app.config['FINTRACK_TOKEN'] or not app.config['FINTRACK_ACCOUNT_ID']:
        print('FinTrack not configured, skipping transaction sync')
        return False
    
    url = f"{app.config['FINTRACK_URL']}/api/transactions/addTransactionFromShortcut"
    headers = {
        'Authorization': f"Bearer {app.config['FINTRACK_TOKEN']}",
        'Content-Type': 'application/json'
    }
    
    # Convert accountId to integer
    try:
        account_id = int(app.config['FINTRACK_ACCOUNT_ID'])
    except (ValueError, TypeError):
        print(f'✗ Invalid FINTRACK_ACCOUNT_ID: must be a number')
        return False
    
    # Use provided date or current date
    if transaction_date is None:
        transaction_date = datetime.utcnow()
    
    # Prepare payload matching FinTrack's expected format
    payload = {
        'userId': account_id,  # accountId for the transaction (must be number)
        'amount': abs(amount),  # Ensure positive
        'type': 'Income',  # Lesson payments are income
        'categoryName': 'Ripetizioni',  # Category for lesson payments
        'notes': notes if notes else 'Lesson payment from Ripetizioni',
        'date': transaction_date.strftime('%Y-%m-%d')  # IMPORTANT: Use the exact payment date
    }
    
    if payment_method:
        payload['notes'] += f' ({payment_method})'
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=5)
        if response.status_code in [200, 201]:
            print(f'✓ Transaction sent to FinTrack: €{amount} on {transaction_date.strftime("%Y-%m-%d")}')
            return True
        else:
            print(f'✗ FinTrack error {response.status_code}: {response.text}')
            return False
    except requests.exceptions.RequestException as e:
        print(f'✗ FinTrack request failed: {e}')
        return False


def delete_from_fintrack(lesson_date: datetime, notes: str) -> bool:
    """
    Delete a transaction from FinTrack when a lesson is marked as unpaid.
    This is a best-effort operation - if it fails, we don't prevent the lesson update.
    Returns True if successful, False otherwise.
    """
    # Skip if FinTrack is not configured
    if not app.config['FINTRACK_TOKEN']:
        print('FinTrack not configured, skipping transaction delete')
        return False
    
    url = f"{app.config['FINTRACK_URL']}/api/transactions/delete-by-details"
    headers = {
        'Authorization': f"Bearer {app.config['FINTRACK_TOKEN']}",
        'Content-Type': 'application/json'
    }
    
    # Prepare payload for deletion
    payload = {
        'date': lesson_date.strftime('%Y-%m-%d'),  # Format: YYYY-MM-DD
        'categoryName': 'Ripetizioni',  # Match the category we used when creating
        'notes': notes  # Match the exact notes we used when creating
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=5)
        if response.status_code in [200, 201, 204]:
            print(f'✓ Transaction deleted from FinTrack: {notes}')
            return True
        else:
            # Log but don't fail - FinTrack delete is not critical
            print(f'⚠ FinTrack delete returned {response.status_code}: {response.text[:200]}')
            print(f'  Payload was: {payload}')
            return False
    except requests.exceptions.RequestException as e:
        # Log but don't fail - FinTrack delete is not critical
        print(f'⚠ FinTrack delete request failed: {e}')
        return False


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.context_processor
def inject_globals():
    """Inject global variables into all templates."""
    return {
        'GOOGLE_CALENDAR_ENABLED': GOOGLE_CALENDAR_ENABLED
    }


def require_token(func):
    """Decorator for endpoints that require an API token (Bearer or ?token=).

    Accepts header Authorization: Bearer <token> or query param token=<token>.
    """
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        token = None
        if auth.lower().startswith('bearer '):
            token = auth.split(None, 1)[1].strip()
        if not token:
            token = request.args.get('token')
        if not token:
            return jsonify({'error': 'token_required'}), 401
        user = User.query.filter_by(api_token=token).first()
        if not user:
            return jsonify({'error': 'invalid_token'}), 403
        # attach user for endpoint use
        request.api_user = user
        return func(*args, **kwargs)

    return wrapper


@app.route('/')
def index():
    # If user is authenticated, show calendar. Otherwise show a welcome page
    if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
        return redirect(url_for('calendar_view'))
    return render_template('welcome.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data).first():
            flash('Email already registered', 'danger')
            return redirect(url_for('register'))
        user = User(email=form.email.data)
        user.set_password(form.password.data)
        user.generate_api_token()
        db.session.add(user)
        db.session.commit()
        flash('Account created, please log in', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            flash('Logged in successfully', 'success')
            return redirect(url_for('calendar_view'))
        flash('Invalid credentials', 'danger')
    return render_template('login.html', form=form)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out', 'info')
    return redirect(url_for('login'))


@app.route('/calendar')
@login_required
def calendar_view():
    # Calendar with month/week views. Params: ?view=month|week & ?date=YYYY-MM-DD
    view = request.args.get('view', 'month')
    date_str = request.args.get('date')
    if date_str:
        try:
            current = datetime.fromisoformat(date_str).date()
        except Exception:
            current = datetime.utcnow().date()
    else:
        current = datetime.utcnow().date()

    def month_grid(target_date):
        # Return list of weeks; each week is list of date objects (Mon-Sun)
        first = target_date.replace(day=1)
        # weekday(): Monday=0
        start = first - timedelta(days=first.weekday())
        # determine last day of month
        if first.month == 12:
            next_month = first.replace(year=first.year+1, month=1, day=1)
        else:
            next_month = first.replace(month=first.month+1, day=1)
        last = next_month - timedelta(days=1)
        end = last + timedelta(days=(6 - last.weekday()))
        # build weeks
        weeks = []
        cur = start
        while cur <= end:
            week = [cur + timedelta(days=i) for i in range(7)]
            weeks.append(week)
            cur = cur + timedelta(days=7)
        return weeks

    def week_grid(target_date):
        start = target_date - timedelta(days=target_date.weekday())
        return [[start + timedelta(days=i) for i in range(7)]]

    if view == 'week':
        weeks = week_grid(current)
        start = weeks[0][0]
        end = weeks[0][-1]
    else:
        weeks = month_grid(current)
        start = weeks[0][0]
        end = weeks[-1][-1]

    # Fetch lessons in the visible range
    lessons = Lesson.query.filter(Lesson.start_datetime >= datetime.combine(start, datetime.min.time()),
                                  Lesson.start_datetime <= datetime.combine(end, datetime.max.time()))
    lessons = lessons.order_by(Lesson.start_datetime).all()
    grouped = {}
    for L in lessons:
        key = L.start_datetime.date().isoformat()
        grouped.setdefault(key, []).append(L)

    # helper URLs for prev/next
    if view == 'week':
        prev_date = (current - timedelta(days=7)).isoformat()
        next_date = (current + timedelta(days=7)).isoformat()
    else:
        # month prev/next
        if current.month == 1:
            prev_month = current.replace(year=current.year-1, month=12, day=1)
        else:
            prev_month = current.replace(month=current.month-1, day=1)
        if current.month == 12:
            next_month = current.replace(year=current.year+1, month=1, day=1)
        else:
            next_month = current.replace(month=current.month+1, day=1)
        prev_date = prev_month.isoformat()
        next_date = next_month.isoformat()

    # pass today's date for correct highlighting
    today = datetime.utcnow().date()
    return render_template('calendar.html', weeks=weeks, grouped=grouped, view=view, current=current, prev_date=prev_date, next_date=next_date, today=today)


@app.route('/lessons')
@login_required
def lessons_view():
    lessons = Lesson.query.order_by(Lesson.start_datetime.desc()).all()
    students = Student.query.order_by(Student.last_name, Student.first_name).all()
    form = LessonForm()
    # provide defaults for the form: default start today at 18:00
    now = datetime.utcnow()
    default_start = datetime(now.year, now.month, now.day, 18, 0)
    form.start_datetime.data = default_start
    return render_template('lessons.html', lessons=lessons, form=form, students=students)


@app.route('/lessons/add', methods=['POST'])
@login_required
def lessons_add():
    form = LessonForm()
    if form.validate_on_submit():
        start = form.start_datetime.data
        # compute end datetime from duration (hours), ensure same day
        dur = float(form.duration.data)
        end = start + timedelta(hours=dur)
        # if end crosses midnight, clamp to same day 23:59
        if end.date() != start.date():
            end = datetime(start.year, start.month, start.day, 23, 59)
        
        # Get student's current hourly_rate to save with the lesson
        student_name = form.student_name.data
        student = Student.query.filter(
            (Student.first_name + ' ' + Student.last_name) == student_name
        ).first()
        hourly_rate = student.hourly_rate if (student and student.hourly_rate) else None
        
        lesson = Lesson(student_name=student_name,
                        start_datetime=start,
                        end_datetime=end,
                        paid=False,
                        hourly_rate=hourly_rate)
        db.session.add(lesson)
        db.session.commit()
        # Create Google Calendar event for the lesson if authorized
        if GOOGLE_CALENDAR_ENABLED:
            try:
                summary = f"Lesson: {lesson.student_name}"
                description = f"Lesson for {lesson.student_name}"
                created = google_calendar.create_event(summary, lesson.start_datetime, lesson.end_datetime, description=description, user=current_user)
                # store created event id on lesson for future sync/delete
                if created and isinstance(created, dict) and created.get('id'):
                    lesson.event_id = created.get('id')
                    db.session.add(lesson)
                    db.session.commit()
            except Exception as e:
                print('Google Calendar create event error:', e)
        flash('Lesson added', 'success')
    else:
        flash('Invalid input', 'danger')
    return redirect(url_for('lessons_view'))


@app.route('/lessons/<int:lesson_id>/add_to_calendar', methods=['POST'])
@login_required
def lessons_add_to_calendar(lesson_id):
    if not GOOGLE_CALENDAR_ENABLED:
        flash('Google Calendar integration is not available', 'danger')
        return redirect(url_for('lessons_view'))
    lesson = Lesson.query.get_or_404(lesson_id)
    try:
        creds = google_calendar.load_credentials()
        if not creds:
            flash('Google Calendar not connected. Please connect first.', 'warning')
            return redirect(url_for('lessons_view'))
        summary = f"Lesson: {lesson.student_name}"
        description = f"Lesson for {lesson.student_name} at {lesson.start_datetime.strftime('%Y-%m-%d %H:%M')}"
        created = google_calendar.create_event(summary, lesson.start_datetime, lesson.end_datetime, description=description, user=current_user)
        if created and isinstance(created, dict) and created.get('id'):
            lesson.event_id = created.get('id')
            db.session.add(lesson)
            db.session.commit()
        flash('Event created in Google Calendar', 'success')
    except Exception as e:
        flash(f'Error creating Google Calendar event: {e}', 'danger')
    return redirect(url_for('lessons_view'))


@app.route('/debug/create_test_event')
def debug_create_test_event():
    """Debug route: create a test event using saved credentials and return API response or error."""
    if not GOOGLE_CALENDAR_ENABLED:
        return jsonify({'error': 'Google Calendar integration is not available'}), 503
    try:
        creds = google_calendar.load_credentials()
        if not creds:
            return jsonify({'error': 'no_credentials'}), 400
        from datetime import datetime, timedelta
        start = datetime.utcnow() + timedelta(minutes=2)
        end = start + timedelta(minutes=30)
        created = google_calendar.create_event('DEBUG EVENT', start, end, description='Debug event')
        return jsonify({'created_id': created.get('id'), 'summary': created.get('summary')}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/lessons/edit/<int:lesson_id>', methods=['POST'])
@login_required
def lessons_edit(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    
    # Get form data directly from request (already_paid not in form)
    student_name = request.form.get('student_name')
    start_datetime_str = request.form.get('start_datetime')
    duration = request.form.get('duration')
    already_paid = bool(request.form.get('already_paid'))
    
    if student_name and start_datetime_str and duration:
        start = datetime.strptime(start_datetime_str, '%Y-%m-%dT%H:%M')
        dur = float(duration)
        end = start + timedelta(hours=dur)
        if end.date() != start.date():
            end = datetime(start.year, start.month, start.day, 23, 59)
        
        lesson.student_name = student_name
        lesson.start_datetime = start
        lesson.end_datetime = end
        lesson.already_paid = already_paid
        
        db.session.commit()
        flash('Lesson updated', 'success')
    else:
        flash('Invalid input', 'danger')
    return redirect(url_for('lessons_view'))


@app.route('/lessons/delete/<int:lesson_id>', methods=['POST'])
@login_required
def lessons_delete(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    db.session.delete(lesson)
    db.session.commit()
    flash('Lesson deleted', 'info')
    return redirect(url_for('lessons_view'))


@app.route('/lessons/delete_multiple', methods=['POST'])
@login_required
def lessons_delete_multiple():
    lesson_ids = request.form.getlist('lesson_ids')
    if lesson_ids:
        deleted_count = 0
        for lesson_id in lesson_ids:
            lesson = Lesson.query.get(int(lesson_id))
            if lesson:
                db.session.delete(lesson)
                deleted_count += 1
        db.session.commit()
        flash(f'{deleted_count} lesson(s) deleted', 'info')
    else:
        flash('No lessons selected', 'warning')
    return redirect(url_for('lessons_view'))


@app.route('/lessons/mark_multiple_paid', methods=['POST'])
@login_required
def lessons_mark_multiple_paid():
    """Mark multiple lessons as paid, grouped by student for FinTrack."""
    data = request.get_json()
    lesson_ids = data.get('lesson_ids', [])
    
    if not lesson_ids:
        return jsonify({'success': False, 'message': 'No lessons selected'})
    
    # Get lessons and group by student
    lessons = Lesson.query.filter(Lesson.id.in_(lesson_ids)).all()
    
    if not lessons:
        return jsonify({'success': False, 'message': 'No valid lessons found'})
    
    # Group lessons by student name
    lessons_by_student = {}
    for lesson in lessons:
        if lesson.paid:
            continue  # Skip already paid lessons
        
        student_name = lesson.student_name
        if student_name not in lessons_by_student:
            lessons_by_student[student_name] = []
        lessons_by_student[student_name].append(lesson)
    
    payment_date = datetime.utcnow()
    fintrack_results = []
    
    # Mark all lessons as paid first
    for lesson in lessons:
        if not lesson.paid:
            lesson.paid = True
            lesson.paid_at = payment_date
            db.session.add(lesson)
    
    db.session.commit()
    
    # Send grouped transactions to FinTrack (one per student)
    for student_name, student_lessons in lessons_by_student.items():
        # Skip if all lessons are already_paid
        lessons_to_bill = [l for l in student_lessons if not l.already_paid]
        
        if not lessons_to_bill:
            fintrack_results.append(f"{student_name}: Skipped (external payment)")
            continue
        
        # Calculate total price for this student
        total_price = sum(l.get_price() for l in lessons_to_bill)
        
        if total_price == 0:
            fintrack_results.append(f"{student_name}: Skipped (no rate set)")
            continue
        
        # Get payment method from first lesson's student
        payment_method = lessons_to_bill[0].get_payment_method()
        
        # Create notes with lesson count and dates
        lesson_count = len(lessons_to_bill)
        date_range = f"{lessons_to_bill[0].start_datetime.strftime('%d/%m')} - {lessons_to_bill[-1].start_datetime.strftime('%d/%m/%Y')}" if len(lessons_to_bill) > 1 else lessons_to_bill[0].start_datetime.strftime('%d/%m/%Y')
        notes = f"{student_name} - {lesson_count} lesson(s) ({date_range})"
        
        # Send to FinTrack
        success = send_to_fintrack(
            amount=total_price,
            notes=notes,
            payment_method=payment_method,
            transaction_date=payment_date
        )
        
        if success:
            fintrack_results.append(f"{student_name}: €{total_price:.2f} synced to FinTrack")
        else:
            fintrack_results.append(f"{student_name}: €{total_price:.2f} (FinTrack sync failed)")
    
    # Build response message
    total_lessons = len([l for l in lessons if not l.paid])
    message = f"Marked {len(lessons)} lesson(s) as paid. " + "; ".join(fintrack_results)
    
    return jsonify({'success': True, 'message': message})


@app.route('/lessons/toggle_paid/<int:lesson_id>', methods=['POST'])
@login_required
def lessons_toggle_paid(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    was_paid = lesson.paid
    lesson.paid = not lesson.paid
    
    # Set paid_at timestamp when marking as paid, clear when marking as unpaid
    payment_date = None
    if lesson.paid:
        payment_date = datetime.utcnow()
        lesson.paid_at = payment_date
    else:
        # Save the paid_at date BEFORE clearing it (needed for FinTrack delete)
        payment_date = lesson.paid_at
        lesson.paid_at = None
    
    db.session.commit()
    
    # If lesson was just marked as PAID (changed from unpaid to paid)
    if not was_paid and lesson.paid:
        # Only send to FinTrack if not already_paid
        if not lesson.already_paid:
            # Send transaction to FinTrack with the exact payment date
            notes = f"{lesson.student_name} - {lesson.start_datetime.strftime('%d/%m/%Y %H:%M')}"
            price = lesson.get_price()
            payment_method = lesson.get_payment_method()
            
            success = send_to_fintrack(
                amount=price,
                notes=notes,
                payment_method=payment_method,
                transaction_date=payment_date  # Pass the exact date we saved in paid_at
            )
            
            if success:
                flash('Lesson marked as paid and synced to FinTrack ✓', 'success')
            else:
                flash('Lesson marked as paid (FinTrack sync failed)', 'warning')
        else:
            # Already paid externally, don't send to FinTrack
            flash('Lesson marked as paid (already paid externally, not sent to FinTrack)', 'info')
    
    # If lesson was just marked as UNPAID (changed from paid to unpaid)
    elif was_paid and not lesson.paid:
        # Only delete from FinTrack if not already_paid
        if not lesson.already_paid:
            # Delete transaction from FinTrack using the SAME date we used when creating it
            notes = f"{lesson.student_name} - {lesson.start_datetime.strftime('%d/%m/%Y %H:%M')}"
            
            # IMPORTANT: Use the saved payment_date (from paid_at before we cleared it)
            # This ensures we delete using the EXACT same date that was sent to FinTrack
            delete_date = payment_date if payment_date else lesson.start_datetime
            
            success = delete_from_fintrack(
                lesson_date=delete_date,
                notes=notes
            )
            
            if success:
                flash('Lesson marked as unpaid and removed from FinTrack', 'success')
            else:
                # Don't show error to user - FinTrack delete is not critical
                # The lesson is still marked as unpaid successfully
                flash('Lesson marked as unpaid', 'info')
        else:
            flash('Lesson marked as unpaid (already paid externally)', 'info')
    
    else:
        flash('Lesson payment status updated', 'success')
    
    return redirect(url_for('lessons_view'))


@app.route('/reports')
@login_required
def reports_view():
    # aggregate by month for the last N months (even if there are no lessons)
    from collections import defaultdict
    months = int(request.args.get('months', 6))
    today = datetime.utcnow().date()
    # build labels for last `months` months (YYYY-MM)
    labels = []
    year = today.year
    month = today.month
    for i in range(months-1, -1, -1):
        m = month - i
        y = year
        while m <= 0:
            m += 12
            y -= 1
        labels.append(f"{y:04d}-{m:02d}")

    data_hours = defaultdict(float)
    data_revenue = defaultdict(float)
    # fetch lessons in range to be efficient
    start_label = labels[0] + "-01"
    end_year, end_month = map(int, labels[-1].split('-'))
    # compute last day of last month
    if end_month == 12:
        end_dt = datetime(end_year+1, 1, 1) - timedelta(seconds=1)
    else:
        end_dt = datetime(end_year, end_month+1, 1) - timedelta(seconds=1)

    lessons = Lesson.query.filter(Lesson.start_datetime >= datetime.fromisoformat(start_label),
                                  Lesson.start_datetime <= end_dt).order_by(Lesson.start_datetime).all()
    for L in lessons:
        key = L.start_datetime.strftime('%Y-%m')
        duration = (L.end_datetime - L.start_datetime).total_seconds() / 3600.0
        data_hours[key] += duration
        if L.paid:
            data_revenue[key] += L.get_price()

    hours = [round(data_hours.get(k, 0.0), 2) for k in labels]
    revenue = [round(data_revenue.get(k, 0.0), 2) for k in labels]
    return render_template('reports.html', labels=labels, hours=hours, revenue=revenue)


### API endpoints for iPhone automation - token protected


@app.route('/api/lessons', methods=['POST'])
@require_token
def api_add_lesson():
    # accept JSON payload
    data = request.get_json() or {}
    # minimal validation
    try:
        student = data['student_name']
        start = datetime.fromisoformat(data['start_datetime'])
    except Exception as e:
        return jsonify({'error': 'invalid_payload', 'message': 'start_datetime missing or invalid'}), 400

    # compute end either from end_datetime or duration (hours)
    end = None
    if 'end_datetime' in data and data.get('end_datetime'):
        try:
            end = datetime.fromisoformat(data['end_datetime'])
        except Exception:
            return jsonify({'error': 'invalid_payload', 'message': 'end_datetime invalid'}), 400
    elif 'duration' in data and data.get('duration'):
        try:
            dur = float(data['duration'])
            end = start + timedelta(hours=dur)
            if end.date() != start.date():
                end = datetime(start.year, start.month, start.day, 23, 59)
        except Exception:
            return jsonify({'error': 'invalid_payload', 'message': 'duration invalid'}), 400
    else:
        return jsonify({'error': 'invalid_payload', 'message': 'end_datetime or duration required'}), 400

    price = float(data.get('price', 0))
    paid = bool(data.get('paid', False))
    lesson = Lesson(student_name=student, start_datetime=start, end_datetime=end, price=price, paid=paid)
    db.session.add(lesson)
    db.session.commit()
    return jsonify({'status': 'created', 'id': lesson.id}), 201


@app.route('/api/students')
@login_required
def api_students():
    # return a list of distinct student names matching query param q
    # use fuzzy matching (difflib) to return similar names when exact match not found
    import difflib
    q = request.args.get('q', '').strip()
    # collect distinct names from DB
    rows = Lesson.query.with_entities(Lesson.student_name).distinct().all()
    names = [r[0] for r in rows if r[0]]
    if not q:
        # return recent distinct names (limit 10)
        return jsonify(sorted(names)[:10])

    # first try simple case-insensitive substring matches (preferred)
    substr_matches = [n for n in names if q.lower() in n.lower()]
    if substr_matches:
        # return up to 10 substring matches, sorted alphabetically
        return jsonify(sorted(substr_matches)[:10])

    # fallback to difflib fuzzy matching
    scores = [(difflib.SequenceMatcher(None, q.lower(), n.lower()).ratio(), n) for n in names]
    scores = sorted(scores, key=lambda x: x[0], reverse=True)
    # take matches above threshold 0.4 and up to 10 results
    results = [n for s, n in scores if s >= 0.4][:10]
    return jsonify(results)


@app.route('/students')
@login_required
def students_list():
    students = Student.query.order_by(Student.last_name, Student.first_name).all()
    return render_template('students.html', students=students)


@app.route('/students/add', methods=['GET', 'POST'])
@login_required
def students_add():
    form = StudentForm()
    if form.validate_on_submit():
        s = Student(first_name=form.first_name.data.strip(),
                    last_name=(form.last_name.data.strip() if form.last_name.data else None),
                    mother_fullname=(form.mother_fullname.data or None),
                    mother_platform=(form.mother_platform.data or None),
                    mother_contact=(form.mother_contact.data or None),
                    payment_method=(form.payment_method.data or None),
                    hourly_rate=(float(form.hourly_rate.data) if form.hourly_rate.data else None),
                    notes=(form.notes.data or None))
        db.session.add(s)
        db.session.commit()
        # Optionally create an event in Google Calendar if authorized and hourly_rate provided
        if GOOGLE_CALENDAR_ENABLED:
            try:
                # This is a simple example: create an all-day event titled "New student: <name>".
                from datetime import datetime, timedelta
                creds = google_calendar.load_credentials()
                if creds:
                    # Create a short event starting now + 1 minute, duration 30 minutes
                    start = datetime.utcnow() + timedelta(minutes=1)
                    end = start + timedelta(minutes=30)
                    summary = f"New student: {s.first_name} {s.last_name or ''}".strip()
                    google_calendar.create_event(summary, start, end, description=s.notes or None)
            except Exception as e:
                # Log but don't block user creation
                print('Google Calendar event error:', e)
        flash('Student created', 'success')
        return redirect(url_for('students_list'))
    return render_template('student_edit.html', form=form)


@app.route('/authorize_calendar')
@login_required
def authorize_calendar():
    if not GOOGLE_CALENDAR_ENABLED:
        flash('Google Calendar integration is not available', 'danger')
        return redirect(url_for('students_list'))
    # Redirect user to Google's OAuth consent screen
    redirect_uri = url_for('oauth2callback', _external=True)
    try:
        auth_url = google_calendar.get_authorize_url(redirect_uri)
        return redirect(auth_url)
    except Exception as e:
        flash(f'Google authorization error: {e}', 'danger')
        return redirect(url_for('students_list'))


@app.route('/oauth2callback')
def oauth2callback():
    if not GOOGLE_CALENDAR_ENABLED:
        flash('Google Calendar integration is not available', 'danger')
        return redirect(url_for('students_list'))
    # Handle OAuth callback and exchange code for token
    try:
        redirect_uri = url_for('oauth2callback', _external=True)
        full_url = request.url
        creds = google_calendar.exchange_code_for_token(full_url, redirect_uri)
        # If user logged in, save credentials to their account
        if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
            try:
                google_calendar.save_credentials_for_user(creds, current_user)
                # Set up webhook for calendar changes
                try:
                    webhook_url = url_for('google_webhook', _external=True)
                    channel_info = google_calendar.watch_calendar(current_user, webhook_url)
                    # Save channel info to user for renewal/stop
                    import json as json_lib
                    current_user.google_channel = json_lib.dumps(channel_info)
                    db.session.add(current_user)
                    db.session.commit()
                    print(f"Webhook registered for user {current_user.id}: {channel_info}")
                except Exception as e:
                    print(f'Error setting up webhook: {e}')
            except Exception as e:
                print('Error saving google creds to user:', e)
        else:
            # fallback: save to instance file
            try:
                google_calendar.save_credentials(creds)
            except Exception:
                pass
        flash('Google Calendar connected successfully', 'success')
    except Exception as e:
        flash(f'Google OAuth error: {e}', 'danger')
    return redirect(url_for('students_list'))


@app.route('/disconnect_calendar')
@login_required
def disconnect_calendar():
    if not GOOGLE_CALENDAR_ENABLED:
        flash('Google Calendar integration is not available', 'danger')
        return redirect(url_for('calendar_view'))
    try:
        # Stop webhook if active
        if current_user.google_channel:
            try:
                import json as json_lib
                channel_info = json_lib.loads(current_user.google_channel)
                google_calendar.stop_channel(channel_info['id'], channel_info['resourceId'], current_user)
            except Exception as e:
                print(f'Error stopping channel: {e}')
        current_user.google_credentials = None
        current_user.google_channel = None
        db.session.add(current_user)
        db.session.commit()
        flash('Disconnected Google Calendar for your account', 'success')
    except Exception as e:
        flash(f'Error disconnecting Google Calendar: {e}', 'danger')
    return redirect(url_for('calendar_view'))


@app.route('/google_webhook', methods=['POST'])
def google_webhook():
    """
    Receive Google Calendar push notifications.
    When calendar changes, Google sends POST here.
    We sync changed events to our Lesson table.
    """
    if not GOOGLE_CALENDAR_ENABLED:
        return '', 503
    # Verify headers sent by Google
    channel_id = request.headers.get('X-Goog-Channel-ID')
    resource_state = request.headers.get('X-Goog-Resource-State')
    
    print(f'Webhook received: channel={channel_id}, state={resource_state}')
    
    # Ignore 'sync' state (initial handshake)
    if resource_state == 'sync':
        return '', 200
    
    if not channel_id:
        print('Webhook missing channel ID')
        return '', 400
    
    # Find user with matching channel_id
    users = User.query.filter(User.google_channel.isnot(None)).all()
    user_found = None
    
    import json as json_lib
    for u in users:
        try:
            channel_info = json_lib.loads(u.google_channel)
            if channel_info.get('id') == channel_id:
                user_found = u
                break
        except:
            continue
    
    if not user_found:
        print(f'No user found for channel {channel_id}')
        return '', 404
    
    # Sync calendar for this user
    import sync_calendar
    sync_calendar.sync_user_calendar(user_found)
    
    return '', 200


@app.route('/sync_calendar_manual')
@login_required
def sync_calendar_manual():
    """Manual sync trigger for testing/debugging."""
    if not GOOGLE_CALENDAR_ENABLED:
        flash('Google Calendar integration is not available', 'danger')
        return redirect(url_for('calendar_view'))
    if not current_user.google_credentials:
        flash('Google Calendar not connected', 'warning')
        return redirect(url_for('calendar_view'))
    
    import sync_calendar
    count = sync_calendar.sync_user_calendar(current_user)
    flash(f'Synced {count} events from Google Calendar', 'success')
    return redirect(url_for('calendar_view'))


@app.route('/students/<int:student_id>', methods=['GET', 'POST'])
@login_required
def student_detail(student_id):
    student = Student.query.get_or_404(student_id)
    topic_form = TopicForm()
    # populate lesson choices for topic relation
    lessons = Lesson.query.filter_by(student_name=f"{student.first_name} {student.last_name}").order_by(Lesson.start_datetime).all()
    choices = [(0, '—')] + [(l.id, l.start_datetime.strftime('%Y-%m-%d %H:%M')) for l in lessons]
    topic_form.lesson_id.choices = choices

    if topic_form.validate_on_submit():
        lid = topic_form.lesson_id.data or None
        if lid == 0:
            lid = None
        t = Topic(student_id=student.id, lesson_id=lid, title=topic_form.title.data.strip(), description=topic_form.description.data)
        db.session.add(t)
        db.session.commit()
        flash('Topic added', 'success')
        return redirect(url_for('student_detail', student_id=student.id))

    topics = Topic.query.filter_by(student_id=student.id).order_by(Topic.created_at.desc()).all()
    photos = StudentPhoto.query.filter_by(student_id=student.id).order_by(StudentPhoto.uploaded_at.desc()).all()
    return render_template('student.html', student=student, topics=topics, photos=photos, topic_form=topic_form)


@app.route('/students/<int:student_id>/upload_photo', methods=['POST'])
@login_required
def student_upload_photo(student_id):
    student = Student.query.get_or_404(student_id)
    if 'photo' not in request.files:
        flash('No file uploaded', 'danger')
        return redirect(url_for('student_detail', student_id=student.id))
    f = request.files['photo']
    if f.filename == '':
        flash('No file selected', 'danger')
        return redirect(url_for('student_detail', student_id=student.id))
    filename = secure_filename(f.filename)
    # prefix with student id + timestamp to avoid collisions
    filename = f"student_{student.id}_{int(datetime.utcnow().timestamp())}_{filename}"
    dest = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    f.save(dest)
    sp = StudentPhoto(student_id=student.id, filename=filename)
    db.session.add(sp)
    db.session.commit()
    flash('Photo uploaded', 'success')
    return redirect(url_for('student_detail', student_id=student.id))


@app.route('/students/<int:student_id>/update_notes', methods=['POST'])
@login_required
def student_update_notes(student_id):
    student = Student.query.get_or_404(student_id)
    notes = request.form.get('notes', '').strip()
    student.notes = notes if notes else None
    db.session.commit()
    flash('Notes updated successfully', 'success')
    return redirect(url_for('student_detail', student_id=student.id))


@app.route('/students/<int:student_id>/update_rate', methods=['POST'])
@login_required
def student_update_rate(student_id):
    student = Student.query.get_or_404(student_id)
    try:
        hourly_rate = request.form.get('hourly_rate', '').strip()
        if hourly_rate:
            student.hourly_rate = float(hourly_rate)
        else:
            student.hourly_rate = None
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/students/<int:student_id>/update', methods=['POST'])
@login_required
def student_update(student_id):
    student = Student.query.get_or_404(student_id)
    try:
        data = request.get_json()
        
        # Update fields dynamically
        allowed_fields = ['mother_fullname', 'mother_platform', 'mother_contact', 
                         'hourly_rate', 'payment_method']
        
        for field, value in data.items():
            if field in allowed_fields:
                if field == 'hourly_rate':
                    student.hourly_rate = float(value) if value else None
                else:
                    setattr(student, field, value if value else None)
        
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/students/<int:student_id>/update_payment', methods=['POST'])
@login_required
def student_update_payment(student_id):
    student = Student.query.get_or_404(student_id)
    try:
        payment_method = request.form.get('payment_method', '').strip()
        student.payment_method = payment_method if payment_method else None
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/students/<int:student_id>/delete', methods=['POST'])
@login_required
def student_delete(student_id):
    student = Student.query.get_or_404(student_id)
    # Delete associated topics
    Topic.query.filter_by(student_id=student.id).delete()
    # Delete associated photos and files
    photos = StudentPhoto.query.filter_by(student_id=student.id).all()
    for photo in photos:
        # Try to delete the physical file
        try:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], photo.filename)
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"Error deleting file {photo.filename}: {e}")
    StudentPhoto.query.filter_by(student_id=student.id).delete()
    # Delete the student
    db.session.delete(student)
    db.session.commit()
    flash(f'Student {student.first_name} {student.last_name} deleted successfully', 'success')
    return redirect(url_for('students_list'))


@app.route('/api/lessons/<int:lesson_id>', methods=['DELETE'])
@require_token
def api_delete_lesson(lesson_id):
    lesson = Lesson.query.get(lesson_id)
    if not lesson:
        return jsonify({'error': 'not_found'}), 404
    db.session.delete(lesson)
    db.session.commit()
    return jsonify({'status': 'deleted'})


if __name__ == '__main__':
    # Enable insecure transport only in development (localhost)
    # In production, HTTPS is required for OAuth
    if os.environ.get('FLASK_ENV') == 'development':
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
        print('WARNING: Running in development mode with OAUTHLIB_INSECURE_TRANSPORT=1')
    
    # ensure database schema is up-to-date inside application context
    with app.app_context():
        # create any missing tables (won't alter existing tables)
        db.create_all()

        # For SQLite, SQLAlchemy won't alter existing tables to add new columns.
        # If the new `payment_method` column is missing in the `lesson` table,
        # add it with a simple ALTER TABLE (safe for SQLite for adding columns).
        try:
            conn = db.engine.connect()
            res = conn.execute("PRAGMA table_info('lesson')").fetchall()
            cols = [r[1] for r in res]
            if 'payment_method' not in cols:
                print('Adding missing column lesson.payment_method')
                conn.execute("ALTER TABLE lesson ADD COLUMN payment_method VARCHAR(64)")
        except Exception as e:
            print('Schema check/alter failed:', e)
        finally:
            try:
                conn.close()
            except Exception:
                pass
    
    # Start webhook renewal scheduler
    if GOOGLE_CALENDAR_ENABLED:
        import webhook_scheduler
        webhook_scheduler.setup_scheduler(app)

    # Use debug mode only in development
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    app.run(debug=debug_mode, host='0.0.0.0')
