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
python -m http.server 5500 --directory frontend
```

Then open http://localhost:5500

The API docs are at http://localhost:8000/docs

## Demo logins

| Role | Email | Password |
|---|---|---|
| Chair | chair@test.com | chair123 |
| Member | alex@test.com, jordan@test.com, sam@test.com, taylor@test.com, morgan@test.com, casey@test.com, riley@test.com | test123 |

Jordan's grades trend down, so that account shows the most flags.

## Start over

Stop the backend, delete `backend/grades.db`, and run `python seed.py --sample` again.

## Notes

- `uvicorn --reload` sometimes doesn't pick up changes on Windows. If the backend seems to be running old code, stop it and start it again.
