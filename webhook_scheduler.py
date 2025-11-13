"""
Background scheduler for webhook renewal.
Google Calendar push notification channels expire after ~7 days.
This scheduler checks daily and renews expiring channels.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import atexit


def setup_scheduler(app):
    """Initialize APScheduler with renewal task."""
    scheduler = BackgroundScheduler()
    
    def renew_webhooks():
        """Renew webhook channels that expire within 24 hours."""
        with app.app_context():
            from models import User
            from extensions import db
            import google_calendar
            import json as json_lib
            from flask import url_for
            
            users = User.query.filter(User.google_channel.isnot(None)).all()
            
            for user in users:
                try:
                    channel_info = json_lib.loads(user.google_channel)
                    expiration = channel_info.get('expiration')
                    
                    if not expiration:
                        continue
                    
                    # expiration is in milliseconds since epoch
                    expiration_dt = datetime.fromtimestamp(int(expiration) / 1000)
                    
                    # Renew if expires within 24 hours
                    if expiration_dt < datetime.utcnow() + timedelta(hours=24):
                        print(f'Renewing webhook for user {user.id}')
                        
                        # Stop old channel
                        google_calendar.stop_channel(
                            channel_info['id'], 
                            channel_info['resourceId'], 
                            user
                        )
                        
                        # Create new channel
                        webhook_url = url_for('google_webhook', _external=True)
                        new_channel_info = google_calendar.watch_calendar(user, webhook_url)
                        
                        # Update DB
                        user.google_channel = json_lib.dumps(new_channel_info)
                        db.session.add(user)
                        db.session.commit()
                        
                        print(f'Renewed webhook for user {user.id}, new expiration: {new_channel_info.get("expiration")}')
                except Exception as e:
                    print(f'Error renewing webhook for user {user.id}: {e}')
    
    # Run daily at 3 AM
    scheduler.add_job(func=renew_webhooks, trigger='cron', hour=3, minute=0, id='renew_webhooks')
    scheduler.start()
    
    # Shut down scheduler when app exits
    atexit.register(lambda: scheduler.shutdown())
    
    print('Webhook renewal scheduler started (runs daily at 3 AM)')
    return scheduler
