# Greek Scholar — Design Doc

## Overview

A web app for a fraternity or sorority scholarship program. Every week, members submit their current grade in each of their classes. The scholarship chair sees everyone's grades, how they change week to week, and flags for members who need attention.

The long-term goal is to support multiple houses and schools. The current version is **one house, run locally**.

## How it works

1. The chair sets up a **term**: first day, last day, and the weekly due day and time (e.g. Sundays at 11:59pm). Every week of the term is generated up front.
2. Each member adds **their classes** for the term (course code, credits). They can add or drop classes at any time. A week's form asks for every current class, plus any class that was dropped *after* that week's deadline, so going back to fix an old week doesn't lose a dropped class's grade.
3. Each week, the member enters a **current % for every class**. The app turns those into letter grades and a credit-weighted GPA using the house's grading scale.
4. A submission made after the deadline still counts for the week it was due, but is marked **late**.
5. Once a deadline passes, members who haven't submitted are marked **missing**.
6. The chair decides which **flags** apply and what their thresholds are.
7. Members can see their own history. The chair can see everyone's.

## Roles

| Role | Can do |
|---|---|
| **Member** | Register, manage their classes, submit weekly grades, view their own history |
| **Chair** | View the members table, member history and house trends; set up terms; edit flag rules and the grading scale; mute flags, correct grades, keep notes, edit, deactivate or delete members |

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
| **User** | name, email, password_hash, role, pledge_class, created_at, active | `created_at` is used so weeks due before someone joined don't count as missing. `active` is false for deactivated members. |
| **Term** | name, start_date, end_date, due_weekday, due_time | `due_weekday`: 0 = Monday … 6 = Sunday |
| **Week** | term_id, number, start_date, due_at | generated when the term is created |
| **Course** | user_id, term_id, code, name, credits, dropped_at | dropping sets `dropped_at` instead of deleting, so past weeks keep the class |
| **Submission** | user_id, week_id, submitted_at, updated_at | one per user per week. `submitted_at` is the *first* submit time and decides late. |
| **ClassGrade** | submission_id, course_id, percent, letter, corrected_at, corrected_by | percent schools fill `percent`, letter schools would fill `letter`. `corrected_*` is set when the chair corrects it. |
| **FlagMute** | user_id, week_id, kind, course_id, label, reason, muted_by, created_at | see Chair management |
| **Note** | user_id, week_id, author_id, text, created_at, updated_at | chair only |
| **AuditLog** | actor_id, action, target_user_id, week_id, course_id, detail, old_value, new_value, reason, created_at | the change log |
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

## Chair management

Every management action is done **as the chair**, through chair-only routes, and is written to the **change log**. The chair never logs in as a member. Every week still has to be submitted; there is no "excused" status.

### Mute a flag

The chair can mute **one flag on one member's week**, with a reason. Example: mute "PHYS 213 below 70%" on week 8 because the member was sick.

- A mute matches the flag's `kind` plus, for class flags, its `course_id`. Muting "PHYS 213 below 70%" doesn't mute "MATH 221 below 70%".
- A muted flag still appears on the member page, grayed out with the reason, so the history is visible.
- A muted flag is skipped by the "Any flag" and per-flag filters, and doesn't give the row a red edge.
- **Status never changes.** A missing week stays missing in the table and in the house missing count.
- `missed_in_row` is muted only on the week it was muted on. If the streak keeps growing, it shows up again the next week, so a mute can't hide a growing problem.
- Members never see flags or mutes.

### Correct a grade

The chair can change one class's % on a week **that already has a submission**. A reason is required.

- The chair can't fill in a missing week. That week has to come from the member.
- On-time/late status doesn't change
- The member sees a **"corrected by chair"** marker on that grade, but not the reason
- If the member resubmits that week later, their new values replace the correction, and the marker goes away. The resubmit is logged too.

### Notes

Private chair notes about a member, either general or tied to one week. The chair can add, edit and delete them. Members never see notes.

### Edit a member

The chair can change a member's **name** and **pledge class**. Email and password belong to the member.

### Remove a member

| Action | What happens | Undo |
|---|---|---|
| **Deactivate** | They can't log in, and any token they already have stops working. They're hidden from the members table, stats, pledge class list and flags. All their data is kept, and the chair can still open their page from "Show inactive". | Reactivate |
| **Permanent delete** | Their account, classes, submissions, grades, notes, mutes and change log entries are all erased. The chair must type the member's full name to confirm, and the backend checks it too. One log entry ("deleted a member") is kept, with the reason but no name. | None |

Only member accounts can be deactivated or deleted; the chair account can't.

### Change log

Every management action, plus every member resubmit that changes a grade, adds a row. Rows are never edited or deleted, except when the member they're about is permanently deleted.

| Action | Logged values |
|---|---|
| `correct_grade` | week, class, old % → new %, reason |
| `resubmit_grade` | week, class, old % → new % (actor is the member) |
| `mute_flag` / `unmute_flag` | week, flag label, reason |
| `add_note` / `edit_note` / `delete_note` | week (if any), note text |
| `edit_member` | field, old → new |
| `deactivate` / `reactivate` | reason |
| `delete_member` | reason only |

### New tables and fields

| Table / field | Fields | Notes |
|---|---|---|
| **FlagMute** | user_id, week_id, kind, course_id, label, reason, muted_by, created_at | unique per user + week + kind + course. `label` keeps the flag text, e.g. "PHYS 213 below 70%". |
| **Note** | user_id, week_id (optional), author_id, text, created_at, updated_at | |
| **AuditLog** | actor_id, action, target_user_id, week_id, course_id, detail, old_value, new_value, reason, created_at | `detail` holds a readable label, e.g. a flag label or a field name |
| `User.active` | bool, default true | |
| `ClassGrade.corrected_at`, `corrected_by` | set when the chair corrects a grade | cleared when the member resubmits |

### New chair routes

| Method | Endpoint | What |
|---|---|---|
| POST | `/members/{id}/weeks/{week_id}/mutes` | mute a flag (`kind`, `course_id`, `reason`) |
| DELETE | `/mutes/{mute_id}` | unmute |
| PUT | `/members/{id}/weeks/{week_id}/grades/{course_id}` | correct a grade (`percent`, `reason`) |
| GET / POST | `/members/{id}/notes` | list / add notes |
| PUT / DELETE | `/notes/{note_id}` | edit / delete a note |
| PATCH | `/members/{id}` | edit name, pledge class |
| POST | `/members/{id}/deactivate`, `/members/{id}/reactivate` | remove / bring back (`reason`) |
| DELETE | `/members/{id}` | permanent delete (`confirm_name`, `reason`) |
| GET | `/members/{id}/log` | change log for a member, newest first |

`/members` also gets `include_inactive`, and every member row and flag says whether it is muted.

### Frontend

- **Member page (chair):**
  - **Header:** Edit, Deactivate / Reactivate, and Delete (a dialog where you type the name)
  - **Each week row:** a mute/unmute button on every flag, and "Correct" on submitted weeks
  - **Panels:** Notes (add, edit, delete) and Change log
- **Chair table:** a "Show inactive" checkbox, muted flags shown gray, and an "Inactive" badge
- **Member history:** a ✎ marker on corrected grades

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
| GET | `/weeks/{id}/courses` | the classes that belong to that week (see below) |
| POST | `/submissions` | `week_id` + `grades: [{course_id, percent}]`. Must include exactly that week's classes. Resubmitting replaces the grades but keeps the original submit time, and every changed grade is logged. |
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
    manage_routes.py   # mutes, corrections, notes, edit, deactivate, delete, change log
    audit.py           # writes change log rows
    tracking.py        # weeks, statuses, history, flags
    grading.py         # grade scale and gpa math
    models.py          # tables and request/response shapes
    database.py        # sqlite setup and default settings
    auth.py            # hashing, tokens, role checks
    seed.py            # chair, term, optional sample data
    requirements.txt
    requirements-dev.txt   # adds pytest for the tests
    tests/             # pytest suite, runs against a throwaway database
  frontend/
    index.html  submit.html  classes.html  history.html
    chair.html  member.html  settings.html
    api.js  app.js  charts.js  style.css
  DESIGN.md
  README.md
```

## Security

- Passwords are hashed with bcrypt. They must be 8+ characters and at most 72 bytes (bcrypt's limit).
- Logging in with a wrong email takes as long as a wrong password, and both give the same message, so you can't tell which emails have accounts. Registering with a used email does say it's taken.
- Tokens are signed with `SECRET_KEY` from the environment, or a random key the backend makes once and keeps in `backend/.secret_key` (git-ignored). Tokens last 24 hours.
- Deactivated or deleted members are locked out right away, even if they still have a token
- Sqlite foreign keys are turned on, so rows can't point at deleted data
- Everything the frontend shows is set with `textContent`, never as HTML, so a name or note can't inject script
- Chart.js loads with an integrity hash, so a changed CDN file won't run
- Members agree to share grades with the chair when they register
- Only the chair can see other members' grades. Members can't see flags.
- The backend checks roles on every route; the frontend checks are only for navigation
- **The chair never logs in as a member.** There is no impersonation or "log in as" feature, and there shouldn't be. The chair sees member data only through chair routes (`/members`, `/members/{id}/history`) using the chair's own token. Any future chair management actions (see below) also go through chair routes and act *on* the member, never *as* them.
- Each browser tab keeps its own login (`sessionStorage`), so logging into a different account in another tab never changes who the current tab is logged in as. Closing the tab logs out.

## Future work

- Letter grade entry and +/- scales for other schools
- Multiple houses (House table + `house_id` on every row) and multiple schools
- Invite links and approving new members
- Email reminders before the deadline, and to members with missing weeks
- Exports (CSV / PDF) for nationals
- Transcript verification at the end of the term
- Handing off the chair role when officers change
- Postgres and deployment
