from __future__ import print_function
import os
import pathlib
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from extensions import db
from models import User
import os
import base64
import hashlib
from cryptography.fernet import Fernet
try:
    from tzlocal import get_localzone
    SERVER_TZ = get_localzone().zone
except Exception:
    SERVER_TZ = os.environ.get('APP_TIMEZONE', 'UTC')


def _get_fernet():
    # Prefer explicit key, otherwise derive from FLASK_SECRET
    secret = os.environ.get('GOOGLE_FERNET_KEY') or os.environ.get('FLASK_SECRET') or os.environ.get('SECRET_KEY') or 'dev_secret'
    # Derive 32-byte key using SHA256 and urlsafe_b64encode
    digest = hashlib.sha256(secret.encode()).digest()
    fkey = base64.urlsafe_b64encode(digest)
    return Fernet(fkey)


def encrypt_text(plain: str) -> str:
    f = _get_fernet()
    token = f.encrypt(plain.encode('utf-8'))
    return token.decode('utf-8')


def decrypt_text(token: str) -> str:
    f = _get_fernet()
    b = f.decrypt(token.encode('utf-8'))
    return b.decode('utf-8')

# Scopes for calendar access (read/write events)
SCOPES = ['https://www.googleapis.com/auth/calendar.events']

# Token storage path (per-user or single file). For simplicity store single token in instance/google_token.json
TOKEN_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'google_token.json')


def build_flow(redirect_uri):
    # Get OAuth credentials from environment variables
    client_id = os.environ.get('GOOGLE_CLIENT_ID')
    client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        raise ValueError('GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables must be set')
    
    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": [redirect_uri]
        }
    }
    
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )
    return flow


def get_authorize_url(redirect_uri):
    flow = build_flow(redirect_uri)
    auth_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true', prompt='consent')
    # Save state to token file temporarily so callback can resume; in a production app you should store state in session
    state_path = TOKEN_PATH + '.state'
    with open(state_path, 'w') as f:
        f.write(state)
    return auth_url


def exchange_code_for_token(request_args, redirect_uri):
    # request_args is the full query string from the callback (Flask's request.args)
    state_path = TOKEN_PATH + '.state'
    if not os.path.exists(state_path):
        raise RuntimeError('OAuth state missing. Start authorization from /authorize_calendar')
    with open(state_path, 'r') as f:
        state = f.read()

    flow = build_flow(redirect_uri)
    flow.fetch_token(authorization_response=request_args)
    creds = flow.credentials
    # clean state
    try:
        os.remove(state_path)
    except Exception:
        pass
    return creds


def save_credentials(creds: Credentials):
    data = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': creds.scopes
    }
    os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
    with open(TOKEN_PATH, 'w') as f:
        json.dump(data, f)


def serialize_credentials(creds: Credentials) -> dict:
    return {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': list(creds.scopes) if creds.scopes else [],
    }


def credentials_from_dict(data: dict) -> Credentials:
    creds = Credentials(
        token=data.get('token'),
        refresh_token=data.get('refresh_token'),
        token_uri=data.get('token_uri'),
        client_id=data.get('client_id'),
        client_secret=data.get('client_secret'),
        scopes=data.get('scopes')
    )
    return creds


def save_credentials_for_user(creds: Credentials, user: User):
    data = serialize_credentials(creds)
    plain = json.dumps(data)
    token = encrypt_text(plain)
    user.google_credentials = token
    db.session.add(user)
    db.session.commit()


def load_credentials_for_user(user: User):
    if not user or not getattr(user, 'google_credentials', None):
        return None
    try:
        token = user.google_credentials
        plain = decrypt_text(token)
        data = json.loads(plain)
    except Exception:
        return None
    creds = credentials_from_dict(data)
    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # save refreshed token back to user
        save_credentials_for_user(creds, user)
    return creds


def load_credentials():
    if not os.path.exists(TOKEN_PATH):
        return None
    with open(TOKEN_PATH, 'r') as f:
        data = json.load(f)
    creds = Credentials(
        token=data.get('token'),
        refresh_token=data.get('refresh_token'),
        token_uri=data.get('token_uri'),
        client_id=data.get('client_id'),
        client_secret=data.get('client_secret'),
        scopes=data.get('scopes')
    )
    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_credentials(creds)
    return creds


def create_event(summary, start_dt, end_dt, description=None, location=None, timezone=SERVER_TZ, user: User = None):
    # Load credentials: prefer per-user if provided, fallback to instance token
    creds = None
    if user:
        creds = load_credentials_for_user(user)
    if not creds:
        creds = load_credentials()
    if not creds:
        raise RuntimeError('No Google credentials available. Authorize first via /authorize_calendar')
    service = build('calendar', 'v3', credentials=creds)

    # Ensure datetime strings include timezone info. If naive, assume UTC and add 'Z'.
    def _fmt(dt):
        if dt.tzinfo is None:
            return dt.isoformat() + 'Z'
        return dt.isoformat()

    event = {
        'summary': summary,
        'start': {'dateTime': _fmt(start_dt), 'timeZone': timezone},
        'end': {'dateTime': _fmt(end_dt), 'timeZone': timezone},
    }
    if description:
        event['description'] = description
    if location:
        event['location'] = location
    created = service.events().insert(calendarId='primary', body=event).execute()
    # Debug log: print created event id and summary
    try:
        print(f"Google Calendar: created event id={created.get('id')} summary={created.get('summary')}")
    except Exception:
        pass
    return created


def watch_calendar(user: User, webhook_url: str):
    """
    Set up push notification for calendar changes.
    Returns channel info dict with id, resourceId, expiration.
    """
    creds = load_credentials_for_user(user)
    if not creds:
        raise RuntimeError('No credentials for user')
    service = build('calendar', 'v3', credentials=creds)
    
    import uuid
    channel_id = f"user_{user.id}_{uuid.uuid4().hex[:8]}"
    body = {
        'id': channel_id,
        'type': 'web_hook',
        'address': webhook_url,
    }
    response = service.events().watch(calendarId='primary', body=body).execute()
    return response


def stop_channel(channel_id: str, resource_id: str, user: User):
    """Stop a notification channel."""
    creds = load_credentials_for_user(user)
    if not creds:
        return
    service = build('calendar', 'v3', credentials=creds)
    body = {
        'id': channel_id,
        'resourceId': resource_id
    }
    try:
        service.channels().stop(body=body).execute()
    except Exception as e:
        print(f"Error stopping channel {channel_id}: {e}")


def list_events(user: User, time_min=None, time_max=None, query=None):
    """
    List calendar events for a user.
    Returns list of event dicts.
    """
    creds = load_credentials_for_user(user)
    if not creds:
        raise RuntimeError('No credentials for user')
    service = build('calendar', 'v3', credentials=creds)
    
    params = {'calendarId': 'primary', 'maxResults': 100, 'singleEvents': True, 'orderBy': 'startTime'}
    if time_min:
        params['timeMin'] = time_min.isoformat() + 'Z' if time_min.tzinfo is None else time_min.isoformat()
    if time_max:
        params['timeMax'] = time_max.isoformat() + 'Z' if time_max.tzinfo is None else time_max.isoformat()
    if query:
        params['q'] = query
    
    events_result = service.events().list(**params).execute()
    return events_result.get('items', [])


def delete_event(event_id: str, user: User):
    """Delete a calendar event by id."""
    creds = load_credentials_for_user(user)
    if not creds:
        raise RuntimeError('No credentials for user')
    service = build('calendar', 'v3', credentials=creds)
    try:
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        print(f"Deleted event {event_id} from Google Calendar")
    except Exception as e:
        print(f"Error deleting event {event_id}: {e}")


def update_event(event_id: str, user: User, summary=None, start_dt=None, end_dt=None, description=None, timezone=SERVER_TZ):
    """Update an existing calendar event."""
    creds = load_credentials_for_user(user)
    if not creds:
        raise RuntimeError('No credentials for user')
    service = build('calendar', 'v3', credentials=creds)
    
    # Fetch existing event
    event = service.events().get(calendarId='primary', eventId=event_id).execute()
    
    # Update fields
    if summary is not None:
        event['summary'] = summary
    if description is not None:
        event['description'] = description
    if start_dt is not None:
        def _fmt(dt):
            if dt.tzinfo is None:
                return dt.isoformat() + 'Z'
            return dt.isoformat()
        event['start'] = {'dateTime': _fmt(start_dt), 'timeZone': timezone}
    if end_dt is not None:
        def _fmt(dt):
            if dt.tzinfo is None:
                return dt.isoformat() + 'Z'
            return dt.isoformat()
        event['end'] = {'dateTime': _fmt(end_dt), 'timeZone': timezone}
    
    updated = service.events().update(calendarId='primary', eventId=event_id, body=event).execute()
    print(f"Updated event {event_id}")
    return updated
