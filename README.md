# Scholarship Tracker

Members submit their grades, and the scholarship chair views and filters them.

See [DESIGN.md](DESIGN.md) for the design doc.

## Backend

FastAPI + SQLite in `backend/`. First time setup:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python seed.py
```

`seed.py` creates the chair account (`chair@test.com` / `chair123` by default, or pass your own: `python seed.py email password`).

Run it:

```bash
uvicorn main:app --reload --port 8000
```

Then open http://localhost:8000/docs to try the endpoints. Click **Authorize** and log in with an email and password to call the protected ones.

The database is `backend/grades.db`. Delete it to start over.

## Frontend (demo)

The frontend is plain HTML/CSS/JS in `frontend/`. For now `api.js` is a fake api that stores data in the browser's localStorage, so it runs without a backend. Later those functions will be swapped for calls to the FastAPI backend.

Run it:

```bash
python -m http.server 5500 --directory frontend
```

Then open http://localhost:5500

Demo logins:

| Role | Email | Password |
|---|---|---|
| Chair | chair@test.com | chair123 |
| Member | alex@test.com | test123 |

Use "Reset demo data" on the login page to start fresh.
