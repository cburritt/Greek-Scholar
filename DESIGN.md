# Scholarship Tracker — Design Doc

## Overview

A simple web app for a fraternity or sorority. Members submit their grades each term, and the scholarship chair views a table of members and their grades with a few basic filters.

The long-term goal is to support multiple houses, statistics, and trend tracking. This document covers the **MVP only**: one house, local API, local database.

## Goals (MVP)

- Members can create an account, log in, and submit their grades for a term
- The scholarship chair can view a table of all members and their grades
- The chair can filter that table by term, pledge class, GPA, and submission status

## Non-goals (for now)

- Multiple houses
- Statistics, charts, or trends
- Invites, email reminders
- Transcript uploads / verification
- Deployment (runs locally only)
- Frontend polish (testing through FastAPI's `/docs` is fine at first)

## Roles

| Role | Can do |
|---|---|
| **Member** | Register, log in, submit grades |
| **Chair** | Log in, view the members table with filters |

There is one chair, created by a seed script. Everyone who registers is a member.

## Tech stack

| Piece | Choice | Why |
|---|---|---|
| Language | Python | Simple |
| Framework | FastAPI | Minimal, built-in `/docs` page for testing |
| Database | SQLite | Single file, no setup |
| ORM | SQLModel | One class serves as both table and API schema |
| Auth | Hashed passwords (bcrypt) + JWT token | Simple and safe enough for an MVP |
| Server | uvicorn | Runs FastAPI locally |

## Data model

### User

| Field | Type | Notes |
|---|---|---|
| id | int | primary key |
| name | str | |
| email | str | unique |
| password_hash | str | never store plain passwords |
| role | str | `member` or `chair` |
| pledge_class | str | e.g. "Fall 2025" |

### GradeSubmission

| Field | Type | Notes |
|---|---|---|
| id | int | primary key |
| user_id | int | foreign key → User |
| term | str | plain text, e.g. "Fall 2026" |
| gpa | float | 0.0 – 4.0 |
| credit_hours | int | must be > 0 |
| submitted_at | datetime | set by server |

Unique on (`user_id`, `term`): one submission per member per term.

No House or Term tables yet. Those get added when multi-house support comes in.

## API

| Method | Endpoint | Who | Description |
|---|---|---|---|
| POST | `/register` | anyone | Create an account (always a member) |
| POST | `/login` | anyone | Returns a token |
| POST | `/grades` | member | Submit grades for a term |
| GET | `/members` | chair | Members table with filters |

### `POST /grades`

Body: `term`, `gpa`, `credit_hours`

- If the member already submitted for that term, the new submission replaces the old one
- Validates GPA range and credit hours

### `GET /members`

Returns one row per member for the selected term:

| name | pledge_class | term | gpa | credit_hours | submitted_at |
|---|---|---|---|---|---|

Members with no submission still appear with blank grade fields so the chair can see who is missing.

Query parameter filters:

| Param | Example | Effect |
|---|---|---|
| `term` | `Fall 2026` | only that term |
| `pledge_class` | `Spring 2025` | only that pledge class |
| `max_gpa` | `2.5` | only members at or below this GPA |
| `submitted` | `false` | only members who have / haven't submitted |
| `sort` | `gpa` or `name` | sort order (optional) |

## Rules

- GPA must be between 0.0 and 4.0
- Credit hours must be positive
- Only the chair can call `/members`; members get `403 Forbidden`
- Members can only submit grades for themselves (user comes from the token, not the request body)

## Project structure

```
scholarship-tracker/
  backend/
    main.py           # routes
    models.py         # User, GradeSubmission, request/response shapes
    database.py       # sqlite setup
    auth.py           # hashing, tokens, chair/member checks
    seed.py           # creates the chair account
    requirements.txt
  frontend/
    index.html        # log in / register
    submit.html       # member grade form
    chair.html        # chair members table
    api.js            # fake api for now, will call the backend
    style.css
  DESIGN.md
  README.md
```

`POST /login` takes a form with `username` (the email) and `password` so the Authorize button in `/docs` works. Both `/register` and `/login` return a token plus the user.

## Build order

1. Models + database + seed chair account
2. Register / login
3. Submit grades
4. Members table + filters
5. Test everything through `/docs`

## Future work

- Simple frontend: submission form for members, table page for the chair
- Statistics: averages, distribution, below-threshold count
- Trends across terms and pledge classes
- Multiple houses (add House table + `house_id` on every row)
- Invites, email reminders
- Transcript verification
- Postgres instead of SQLite, deployment

## Privacy notes

Grades are sensitive. Even in the MVP:

- Passwords are hashed
- Only the chair can see other members' grades
- Members should agree to share grades with the chair when they register
