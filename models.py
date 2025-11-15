from extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import secrets


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    api_token = db.Column(db.String(128), unique=True, index=True)
    # JSON serialized Google credentials for per-user calendar integration
    google_credentials = db.Column(db.Text, nullable=True)
    # Google Calendar webhook channel info (JSON: {id, resourceId, expiration})
    google_channel = db.Column(db.Text, nullable=True)
    # User profile
    first_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    # FinTrack integration (per-user)
    fintrack_token = db.Column(db.Text, nullable=True)  # JWT token
    fintrack_account_id = db.Column(db.Integer, nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_api_token(self):
        self.api_token = secrets.token_urlsafe(32)
        return self.api_token


class Lesson(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_name = db.Column(db.String(200), nullable=False)
    start_datetime = db.Column(db.DateTime, nullable=False)
    end_datetime = db.Column(db.DateTime, nullable=False)
    paid = db.Column(db.Boolean, default=False)
    paid_at = db.Column(db.DateTime, nullable=True)  # When the lesson was marked as paid
    event_id = db.Column(db.String(255), nullable=True)  # Google Calendar event id
    already_paid = db.Column(db.Boolean, default=False)  # If True, skip FinTrack when marking as paid
    hourly_rate = db.Column(db.Float, nullable=True)  # Hourly rate at time of lesson creation (historical price)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def duration_hours(self):
        return (self.end_datetime - self.start_datetime).total_seconds() / 3600.0
    
    def get_student(self):
        """Get the Student object for this lesson, if exists."""
        return Student.query.filter(
            (Student.first_name + ' ' + Student.last_name) == self.student_name
        ).first()
    
    def get_price(self):
        """Get the price for this lesson from the lesson's hourly rate or student's hourly rate."""
        # Use lesson's hourly_rate if set (historical price at time of creation)
        if self.hourly_rate is not None:
            return self.hourly_rate * self.duration_hours()
        
        # Fallback to student's current hourly_rate (for old lessons without hourly_rate)
        student = self.get_student()
        if student and student.hourly_rate:
            return student.hourly_rate * self.duration_hours()
        return 0.0
    
    def get_payment_method(self):
        """Get the payment method from the student's preferred method."""
        student = self.get_student()
        return student.payment_method if student else None


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(120), nullable=False)
    last_name = db.Column(db.String(120), nullable=True)
    mother_fullname = db.Column(db.String(255), nullable=True)
    mother_platform = db.Column(db.String(32), nullable=True)  # 'messenger' or 'whatsapp'
    mother_contact = db.Column(db.String(255), nullable=True)  # nickname or phone number
    payment_method = db.Column(db.String(64), nullable=True)  # 'cash', 'paypal', 'bank'
    hourly_rate = db.Column(db.Float, nullable=True)  # Price per hour
    notes = db.Column(db.Text, nullable=True)
    photos = db.relationship('StudentPhoto', backref='student', lazy=True)


class Topic(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    lesson_id = db.Column(db.Integer, db.ForeignKey('lesson.id'), nullable=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class StudentPhoto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
