# Ripetizioni Manager

Simple Flask app to manage tutoring lessons (lessons, calendar, reports) with authentication and token-protected API endpoints for automation.

## Features

- 📅 Calendar view of all lessons
- 👨‍🎓 Student management with photos, topics, and contact information
- 💰 Payment tracking with multiple payment methods (cash, PayPal, bank transfer)
- 📊 Revenue reports and charts
- 🔗 **FinTrack Integration**: Automatically sync paid lessons to your FinTrack expense tracker

## 🐳 Quick Start with Docker (Recommended)

1. **Configure environment variables:**
   
   Copy `.env.example` to `.env` and configure your settings:
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` with your values (at minimum set FLASK_SECRET).

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

## 🔒 Security Notes

- This is a development scaffold. Before production: enable HTTPS, rotate secrets, use a stronger DB, and consider rate-limiting the token endpoints.
- API endpoints accept a bearer token in Authorization header or ?token= query param. Keep tokens secret.
- The app uses Tailwind via the Play CDN for rapid responsive styling (development only). For production, precompile Tailwind or use a stable build.

## 📝 Next Steps

- Implement lesson modification via API.
- Replace placeholder chart.min.js with official Chart.js from a CDN for better visuals.
