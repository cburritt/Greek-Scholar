# Greek Scholar

Members submit their class grades every week, and the scholarship chair tracks them over the term with filters, flags, and charts.

See [DESIGN.md](DESIGN.md) for the design doc.

## Setup (first time)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python seed.py --sample
```

`seed.py` creates the chair account and the Fall 2026 term. `--sample` also adds 7 demo members with classes and weekly grades. Leave it off for an empty house.

To use your own chair login: `python seed.py email password`

## Run it

Two terminals.

Backend (from `backend/`, with the venv active):

```bash
uvicorn main:app --port 8000
```

Frontend (from the repo root):

```bash
python serve_frontend.py
```

This is a tiny server that tells the browser not to cache, so code changes show up on a normal reload. (`python -m http.server 5500 --directory frontend` also works, but the browser may keep old copies of the scripts; press Ctrl+Shift+R if a change doesn't show.)

Then open http://localhost:5500

The API docs are at http://localhost:8000/docs

## Demo logins

| Role | Email | Password |
|---|---|---|
| Chair | chair@test.com | chair123 |
| Member | alex@test.com, jordan@test.com, sam@test.com, taylor@test.com, morgan@test.com, casey@test.com, riley@test.com | test123 |

Every sample submission has a generated "Canvas" screenshot, so the 📷 buttons work. Those images are in `backend/uploads/`, which is git-ignored.

Jordan's grades trend down, so that account shows the most flags. It also has a sample note, a corrected grade and a muted flag. Riley is deactivated, so Riley can't log in and only shows up with "Show inactive members".

The demo passwords are shorter than the 8 characters new accounts need. That's fine for the demo, but change the chair password before real use: `python seed.py youremail yourpassword`.

## Tests

From `backend/`, with the venv active:

```bash
pip install -r requirements-dev.txt
python -m pytest tests
```

The tests use their own throwaway database, so they never touch `grades.db`.

## Start over

Stop the backend, delete `backend/grades.db`, and run `python seed.py --sample` again. You have to do this after pulling changes that add database columns; the backend will tell you if so. You can also delete `backend/uploads/` to clear old screenshots.

## Notes

- `uvicorn --reload` sometimes doesn't pick up changes on Windows. If the backend seems to be running old code, stop it and start it again.
