# Lessons Manager

Flask application to manage tutoring lessons with Google Calendar integration, student tracking, payment management, and automated expense sync with FinTrack.

## ✨ Features

- 📅 **Calendar View**: Month/week view of all lessons
- 👨‍🎓 **Student Management**: Photos, topics, contact information, and hourly rates
- 💰 **Payment Tracking**: Multiple payment methods (cash, PayPal, bank transfer)
- 📊 **Revenue Reports**: Charts and financial analytics
- 🔗 **FinTrack Integration**: Auto-sync paid lessons to expense tracker
- 📆 **Google Calendar Sync**: Bidirectional sync with personal Google Calendar
  - Add lessons in app → Creates calendar event
  - Add "Ripetizioni <name>" event in Google → Creates lesson in app
  - Webhook-based real-time updates
  - Per-user OAuth (each user connects their own calendar)

## 🚀 Quick Start (Development)

### Using Docker (Recommended)

1. **Configure environment variables:**
   
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` with your values:
   ```dotenv
   FLASK_ENV=development
   FLASK_SECRET=your-secret-key
   GOOGLE_CLIENT_ID=your-google-client-id
   GOOGLE_CLIENT_SECRET=your-google-client-secret
   ```
   
   > **Note**: For development, Google OAuth will work with `http://localhost`. For production, see [DEPLOYMENT.md](DEPLOYMENT.md).

2. **Build and start the container:**
   ```bash
   docker-compose up --build
   ```

3. **Initialize the database (first time only):**
   
   In another terminal:
   ```bash
   docker-compose exec web python init_db.py --email your@email.com --password YourPassword123
   ```

4. **Open the app:**
   
   Navigate to http://localhost:5001 and login with your credentials.

5. **Stop the container:**
   ```bash
   docker-compose down
   ```

### Docker Notes:
- Database is persisted in `./instance/` folder (mounted as volume)
- Uploaded photos are persisted in `./static/uploads/` folder
- To rebuild after code changes: `docker-compose up --build`
- All configuration is in `.env` file

## 💻 Quick start (local development):

1. Create a Python virtualenv and activate it.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. (Optional) Configure FinTrack integration:
   
   Copy `.env.example` to `.env` and fill in your FinTrack details:
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env`:
   ```bash
   FLASK_SECRET=your-secret-key-here
   FINTRACK_URL=http://localhost:3000
   FINTRACK_TOKEN=your-bearer-token
   FINTRACK_ACCOUNT_ID=your-account-id
   ```

4. **Initialize the database:**

   ```bash
   python init_db.py --email your@domain.com --password yourpassword
   ```

5. **Run the app:**

   ```bash
   python app.py
   ```

6. **Open the app:**
   
   Navigate to http://127.0.0.1:5000 and login with your credentials.

## ⚙️ FinTrack Integration

When you mark a lesson as **paid**, Ripetizioni will automatically send a transaction to FinTrack:

- **Type**: Income
- **Amount**: Lesson hourly rate
- **Notes**: Student name, date, and payment method
- **Category**: "Da categorizzare" (auto-created if missing)

If FinTrack is not configured, lessons will still work normally without syncing.

## 📦 Production Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for complete production deployment guide including:
- HTTPS setup (required for Google OAuth)
- Nginx reverse proxy configuration
- Security best practices
- Backup and restore procedures

## 🔒 Security Notes

- **Development**: Uses `OAUTHLIB_INSECURE_TRANSPORT=1` for local testing
- **Production**: Requires HTTPS for Google OAuth (automatically enforced)
- API endpoints use bearer token authentication
- Passwords are hashed with Werkzeug security
- Google credentials are encrypted with Fernet (key derived from FLASK_SECRET)

## 🔧 Configuration

### Required Environment Variables

- `FLASK_SECRET`: Secret key for session encryption (generate with `python -c "import secrets; print(secrets.token_hex(32))"`)
- `GOOGLE_CLIENT_ID`: Google OAuth client ID
- `GOOGLE_CLIENT_SECRET`: Google OAuth client secret

### Optional Environment Variables

- `FLASK_ENV`: `development` or `production` (default: `production`)
- `FINTRACK_URL`: FinTrack instance URL
- `FINTRACK_TOKEN`: FinTrack JWT token
- `FINTRACK_ACCOUNT_ID`: FinTrack account ID

## 📝 Next Steps / Roadmap

- [ ] Email notifications for upcoming lessons
- [ ] Recurring lesson templates
- [ ] Multi-currency support
- [ ] Mobile app (React Native)
- [ ] SMS reminders integration

## 🐛 Troubleshooting

See [DEPLOYMENT.md](DEPLOYMENT.md) for common issues and solutions.

## 📄 License

MIT License - See LICENSE file for details
