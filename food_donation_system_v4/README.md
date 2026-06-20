# 🍱 Food Donation System — v2 Enhanced

## What's New in v2

### 🐛 Bug Fix
- **NGO Dashboard crash fixed** — `TypeError: Object of type Row is not JSON serializable`
  Caused by passing raw `sqlite3.Row` objects to Jinja's `tojson` filter.
  Fixed by converting all Row objects to plain dicts before rendering templates and JSON responses.

### 🥦 Food Category Filtering
- 6 categories: **Veg, Non-Veg, Fruits, Bakery, Cooked Meals, Packaged Food**
- Category dropdown in the Donate form
- Category filter buttons on the NGO Dashboard (with live counts)
- Category badges shown on every donation card and table row
- Category column in admin PDF report

### 💬 Real-Time Chat (Flask-SocketIO)
- **Per-donation chat rooms** — one room created automatically when an NGO accepts a donation
- **Live messaging** via WebSocket — no page refresh needed
- Donor sees a 💬 Chat button once their donation is accepted
- NGO sees a Chat button on each accepted donation card
- Messages stored in `chat_messages` table with timestamps
- Colour-coded avatars: green = donor, blue = NGO, red = admin

## Setup

```bash
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000

| Account       | Email              | Password  |
|---------------|--------------------|-----------|
| Admin         | admin@food.com     | admin123  |
| Create NGO    | Sign up → role NGO |           |
| Create Donor  | Sign up → role Donor|          |

## Project Structure

```
food_donation_system_v2/
├── app.py                  ← Main Flask + SocketIO app
├── requirements.txt
├── static/
│   ├── style.css
│   └── script.js
└── templates/
    ├── chat.html           ← NEW: Real-time chat page
    ├── ngo_dashboard.html  ← FIXED + enhanced with category filters
    ├── donate.html         ← Category dropdown added
    ├── dashboard.html      ← Category badge + chat button
    └── ...
```
