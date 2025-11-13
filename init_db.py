"""Utility to initialize the database and create an initial user.

Run: python init_db.py --email you@example.com --password secret
This will create the sqlite DB and a user with an API token printed to stdout.
"""
import argparse
from app import app
from extensions import db
from models import User


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--email', required=True)
    parser.add_argument('--password', required=True)
    args = parser.parse_args()

    # Ensure we run DB operations inside the Flask application context
    with app.app_context():
        db.create_all()
        if User.query.filter_by(email=args.email).first():
            print('User already exists')
            return
        u = User(email=args.email)
        u.set_password(args.password)
        token = u.generate_api_token()
        db.session.add(u)
        db.session.commit()
        print('Created user:', args.email)
        print('API token:', token)


if __name__ == '__main__':
    main()
