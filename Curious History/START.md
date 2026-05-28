# Curious History — Quick Start

## Run the app
```
python3 app.py
```
Then open: **http://127.0.0.1:5001**

## Note on Gemini API
If you see "Content generation temporarily unavailable" — your free-tier quota is
exhausted for the day. It resets every 24 hours. The app still works for navigation;
Gemini-powered features (article synthesis, summaries, quizzes) need the quota to be available.

## Supabase (optional)
Fill in SUPABASE_URL and SUPABASE_ANON_KEY in `.env` to enable:
- Saved events / quotes sync across devices
- Emoji reaction counts
- Search history

Without Supabase, everything works via localStorage.
