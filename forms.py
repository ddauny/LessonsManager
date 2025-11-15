from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, DateTimeField, DecimalField, SubmitField, SelectField, IntegerField
from wtforms.validators import DataRequired, Email, Length, Optional


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')


class RegisterForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    submit = SubmitField('Register')


class ProfileForm(FlaskForm):
    first_name = StringField('First Name', validators=[Optional()])
    last_name = StringField('Last Name', validators=[Optional()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    current_password = PasswordField('Current Password (required to save changes)', validators=[Optional()])
    new_password = PasswordField('New Password (leave empty to keep current)', validators=[Optional(), Length(min=6)])
    confirm_password = PasswordField('Confirm New Password', validators=[Optional()])
    # FinTrack integration
    fintrack_token = StringField('FinTrack JWT Token', validators=[Optional()])
    fintrack_account_id = IntegerField('FinTrack Account ID', validators=[Optional()])
    submit = SubmitField('Save Profile')


class LessonForm(FlaskForm):
    student_name = StringField('Student name', validators=[DataRequired()])
    # start datetime uses HTML datetime-local format
    start_datetime = DateTimeField('Start datetime', format='%Y-%m-%dT%H:%M', validators=[DataRequired()])
    # duration in hours (e.g. 1, 1.5, 2)
    duration = SelectField('Duration (hours)', choices=[('1', '1'), ('1.5', '1.5'), ('2', '2')], default='1')
    submit = SubmitField('Save')


class StudentForm(FlaskForm):
    first_name = StringField('First name', validators=[DataRequired()])
    last_name = StringField('Last name')
    mother_fullname = StringField("Mother's full name")
    mother_platform = SelectField("Mother's platform", choices=[('', '—'), ('messenger','Messenger'), ('whatsapp','WhatsApp')], default='')
    mother_contact = StringField("Mother's contact (nickname or phone number)")
    payment_method = SelectField('Payment method', choices=[('', '—'), ('cash', 'Cash'), ('paypal', 'PayPal'), ('bank', 'Bank transfer')], default='')
    hourly_rate = DecimalField('Hourly rate (€)', places=2)
    notes = StringField('Notes')
    submit = SubmitField('Save')


class TopicForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired()])
    description = StringField('Description')
    lesson_id = SelectField('Related lesson', choices=[], coerce=int, default=0)
    submit = SubmitField('Add topic')
