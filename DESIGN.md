# Greek Scholar — Design Doc

## Overview

A web app for a fraternity or sorority scholarship program. Every week, members submit their current grade in each of their classes. The scholarship chair sees everyone's grades, how they change week to week, and flags for members who need attention.

The long-term goal is to support multiple houses and schools. The current version is **one house, run locally**.

## How it works

1. The chair sets up a **term**: first day, last day, and the weekly due day and time (e.g. Sundays at 11:59pm). Every week of the term is generated up front.
2. Each member adds **their classes** for the term (course code, credits). They can add or drop classes at any time.
3. Each week, the member enters a **current % for every class**. The app turns those into letter grades and a credit-weighted GPA using the house's grading scale.
4. A submission made after the deadline still counts for the week it was due, but is marked **late**.
5. Once a deadline passes, members who haven't submitted are marked **missing**.
6. The chair decides which **flags** apply and what their thresholds are.
7. Members can see their own history. The chair can see everyone's.

## Roles

| Role | Can do |
|---|---|
| **Member** | Register, manage their classes, submit weekly grades, view their own history |
| **Chair** | View the members table, member history and house trends; set up terms; edit flag rules and the grading scale |

There is one chair, created by the seed script. Everyone who registers is a member.

## Tech stack

| Piece | Choice | Why |
|---|---|---|
| Backend | Python, FastAPI | Minimal, built-in `/docs` page for testing |
| Database | SQLite via SQLModel | Single file, one class is both table and schema |
| Auth | bcrypt password hashes + JWT tokens | Simple and safe enough for now |
| Frontend | Plain HTML/CSS/JS | No build step |
| Charts | Chart.js (CDN) | Simple line and bar charts |

## Data model

| Table | Fields | Notes |
|---|---|---|
| **User** | name, email, password_hash, role, pledge_class, created_at | `created_at` is used so weeks due before someone joined don't count as missing |
| **Term** | name, start_date, end_date, due_weekday, due_time | `due_weekday`: 0 = Monday … 6 = Sunday |
| **Week** | term_id, number, start_date, due_at | generated when the term is created |
| **Course** | user_id, term_id, code, name, credits, dropped_at | dropping sets `dropped_at` instead of deleting, so past weeks keep the class |
| **Submission** | user_id, week_id, submitted_at, updated_at | one per user per week. `submitted_at` is the *first* submit time and decides late. |
| **ClassGrade** | submission_id, course_id, percent, letter | percent schools fill `percent`, letter schools would fill `letter` |
| **GradeScale** | letter, min_percent, points | editable by the chair |
| **FlagRule** | kind, threshold, enabled | editable by the chair |
| **HouseSettings** | grade_entry | `percent` for now, `letter` later |

GPA is never stored. It is calculated from the class grades, the course credits and the current scale, so editing the scale updates every week.

### Current term

The current term is the **newest term that has started**. That way the chair can set up next term early without hiding this one. If only future terms exist, the soonest one is used.

### Week status

For each member and week:

| Status | Meaning |
|---|---|
| `on_time` | submitted before the deadline |
| `late` | submitted after the deadline |
| `missing` | deadline passed, nothing submitted |
| `open` | not due yet, nothing submitted |
| `not_member` | the week was due before they made an account |

## Grading

Members enter a percent for each class (0–120, to allow extra credit). The default scale:

| Letter | Min % | Points |
|---|---|---|
| A | 90 | 4.0 |
| B | 80 | 3.0 |
| C | 70 | 2.0 |
| D | 60 | 1.0 |
| F | 0 | 0.0 |

GPA = sum(points × credits) / sum(credits).

The scale is a table, so +/- grades just mean adding rows (A-, B+, …). Saving a scale is rejected unless:
- some row starts at 0
- letters and minimums are unique
- a higher cutoff is never worth fewer points

**Planned:** schools that only give letter grades. `HouseSettings.grade_entry = "letter"` would make the submit form show a letter dropdown, and fill `ClassGrade.letter` instead of `percent`. GPA math already goes letter → points, so it works the same way.

## Flags

Flags are calculated whenever a week is loaded, so changing a rule updates the whole term right away. Each rule can be turned on or off, and its threshold edited, in Settings.

| Kind | Default | Triggers when |
|---|---|---|
| `missing` | on | the week is missing |
| `late` | on | the week was submitted late |
| `gpa_below` | 2.5 | GPA for the week is below the threshold |
| `class_below` | 70% | any class is below the threshold |
| `gpa_drop` | 0.3 | GPA dropped at least this much since the week before |
| `class_drop` | 10% | a class dropped at least this much since the week before (only compares classes in both weeks) |
| `missed_in_row` | 2 | this many missing weeks in a row, ending at this week |

Members never see flags.

## API

### Auth
| Method | Endpoint | Description |
|---|---|---|
| POST | `/register` | create a member account, returns token + user |
| POST | `/login` | form with `username` (email) + `password`, returns token + user |
| GET | `/me` | the logged in user |

### Shared
| Method | Endpoint | Description |
|---|---|---|
| GET | `/terms/current` | current term, or null |
| GET | `/weeks` | started weeks of the current term, newest first. Members also get their status for each week. |
| GET | `/settings/grade-scale` | the grading scale |
| GET | `/settings/house` | house settings (grade entry mode) |

### Member
| Method | Endpoint | Description |
|---|---|---|
| GET | `/courses?include_dropped=` | their classes this term |
| POST | `/courses` | add a class (`code`, `name`, `credits`) |
| DELETE | `/courses/{id}` | drop a class (kept for history) |
| POST | `/submissions` | `week_id` + `grades: [{course_id, percent}]`. Must include every active class. Resubmitting replaces the grades but keeps the original submit time. |
| GET | `/submissions/me` | their history: every week with status, GPA, change, class grades |

### Chair
| Method | Endpoint | Description |
|---|---|---|
| GET/POST | `/terms` | list terms / create a term (weeks are generated) |
| GET | `/members` | one row per member for a week. Params: `week_id` (defaults to newest), `pledge_class`, `status` (`on_time`, `late`, `missing`, `open`, `submitted`), `flag` (a kind or `any`), `sort` (`name`, `gpa`, `change`) |
| GET | `/members/{id}/history` | one member's weeks with flags |
| GET | `/stats/weekly` | per week: average GPA, on time, late, missing, expected |
| GET | `/pledge-classes` | for the filter dropdown |
| GET/PUT | `/settings/flags` | flag rules |
| PUT | `/settings/grade-scale` | replace the scale |

## Frontend pages

| Page | Who | What |
|---|---|---|
| `index.html` | anyone | log in / create account (new members go to My classes) |
| `submit.html` | member | pick a week (defaults to the oldest missing one), enter % per class with a live letter + GPA preview. Shows a banner for missed weeks. |
| `classes.html` | member | add / drop classes, see dropped ones |
| `history.html` | member | GPA chart, class grade chart, week-by-week table |
| `chair.html` | chair | house trend chart + stats for the week, members table with filters. Opens on the newest week that is already due. |
| `member.html` | chair | one member's charts and week table with flags |
| `settings.html` | chair | flag rules, grading scale, create a term |

`api.js` has every call to the backend, `app.js` has shared helpers (header, badges, formatting), and `charts.js` has the charts and history table.

## Project structure

```
scholarship-tracker/
  backend/
    main.py            # app setup, auth and shared routes
    member_routes.py   # classes and submissions
    chair_routes.py    # members table, history, stats, terms, settings
    tracking.py        # weeks, statuses, history, flags
    grading.py         # grade scale and gpa math
    models.py          # tables and request/response shapes
    database.py        # sqlite setup and default settings
    auth.py            # hashing, tokens, role checks
    seed.py            # chair, term, optional sample data
    requirements.txt
  frontend/
    index.html  submit.html  classes.html  history.html
    chair.html  member.html  settings.html
    api.js  app.js  charts.js  style.css
  DESIGN.md
  README.md
```

## Privacy

- Passwords are hashed
- Members agree to share grades with the chair when they register
- Only the chair can see other members' grades. Members can't see flags.
- The backend checks roles on every route; the frontend checks are only for navigation
- **The chair never logs in as a member.** There is no impersonation or "log in as" feature, and there shouldn't be. The chair sees member data only through chair routes (`/members`, `/members/{id}/history`) using the chair's own token. Any future chair management actions (see below) also go through chair routes and act *on* the member, never *as* them.
- Each browser tab keeps its own login (`sessionStorage`), so logging into a different account in another tab never changes who the current tab is logged in as. Closing the tab logs out.

## Future work

- Chair management of members, done as the chair, not by logging in as them:
  - excuse a missing week (e.g. illness) so it isn't flagged
  - add a note to a member or a week
  - change a member's pledge class, or remove someone who left the house
  - correct a grade, with the change recorded (who, when, old value)
- Letter grade entry and +/- scales for other schools
- Multiple houses (House table + `house_id` on every row) and multiple schools
- Invite links and approving new members
- Email reminders before the deadline, and to members with missing weeks
- Exports (CSV / PDF) for nationals
- Transcript verification at the end of the term
- Handing off the chair role when officers change
- Postgres and deployment
