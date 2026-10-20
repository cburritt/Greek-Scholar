# sets up the chair account and a term
# usage: python seed.py [--sample] [email] [password]
#   --sample also adds demo members with classes and weekly grades

import random
import sys
from datetime import date, datetime, time, timedelta

from sqlmodel import Session, select

from audit import fmt_percent, log
from auth import hash_password
from database import create_db, engine
from models import ClassGrade, Course, FlagMute, Note, Submission, Term, User, Week
from tracking import generate_weeks

args = [a for a in sys.argv[1:] if a != "--sample"]
add_sample = "--sample" in sys.argv

email = "chair@test.com"
password = "chair123"
if len(args) > 0:
    email = args[0].strip().lower()
if len(args) > 1:
    password = args[1]

create_db()


def seed_chair(session: Session):
    existing = session.exec(select(User).where(User.email == email)).first()
    if existing:
        existing.role = "chair"
        session.add(existing)
        session.commit()
        print(f"{email} already exists, made sure it is the chair")
        return
    session.add(User(name="Chair", email=email, password_hash=hash_password(password), role="chair"))
    session.commit()
    print(f"created chair account {email}")


def seed_term(session: Session) -> Term:
    term = session.exec(select(Term)).first()
    if term:
        print(f"term {term.name} already exists")
        return term

    # grades due sunday night
    term = Term(name="Fall 2026", start_date=date(2026, 8, 17), end_date=date(2026, 12, 11), due_weekday=6, due_time=time(23, 59))
    session.add(term)
    session.commit()
    session.refresh(term)
    for week in generate_weeks(term):
        session.add(week)
    session.commit()
    print(f"created term {term.name}")
    return term


SAMPLE_MEMBERS = [
    # name, pledge class, how their grades trend each week
    ("Alex Carter", "Fall 2024", 0.3),
    ("Jordan Lee", "Fall 2024", -0.9),
    ("Sam Rivera", "Spring 2025", 0.0),
    ("Taylor Brooks", "Spring 2025", 0.5),
    ("Morgan Diaz", "Fall 2025", -0.6),
    ("Casey Nguyen", "Fall 2025", 0.1),
    ("Riley Patel", "Spring 2026", -0.2),
]

COURSE_POOL = [
    ("CIS 501", 3), ("CIS 505", 3), ("MATH 221", 4), ("STAT 325", 3), ("ENGL 200", 3),
    ("PHYS 213", 4), ("ECON 110", 3), ("COMM 106", 2), ("BIOL 198", 4), ("PSYCH 110", 3),
]


def seed_sample(session: Session, term: Term):
    if session.exec(select(User).where(User.role == "member")).first():
        print("members already exist, skipping sample data")
        return

    rng = random.Random(42)
    weeks = session.exec(select(Week).where(Week.term_id == term.id).order_by(Week.number)).all()
    now = datetime.now()
    started = [w for w in weeks if w.start_date <= now.date()]

    for i, (name, pledge_class, trend) in enumerate(SAMPLE_MEMBERS):
        first = name.split()[0].lower()
        user = User(
            name=name,
            email=f"{first}@test.com",
            password_hash=hash_password("test123"),
            pledge_class=pledge_class,
            created_at=datetime(2026, 8, 1),
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        courses = []
        for code, credits in rng.sample(COURSE_POOL, 4):
            course = Course(user_id=user.id, term_id=term.id, code=code, credits=credits, created_at=datetime(2026, 8, 17))
            session.add(course)
            courses.append(course)
        session.commit()

        # the second member drops a class after week 5
        drop_after = None
        if i == 1:
            drop_after = 5
            courses[-1].dropped_at = datetime.combine(weeks[5].start_date, time(12))
            session.add(courses[-1])
            session.commit()

        base = {c.id: rng.uniform(72, 95) for c in courses}

        for week in started:
            is_open = week.due_at > now
            roll = rng.random()
            # most people have not turned in the current week yet
            if is_open and roll < 0.7:
                continue
            if not is_open and roll < 0.08:
                continue  # missing

            submitted_at = week.due_at - timedelta(days=1)
            if not is_open and roll < 0.18:
                submitted_at = week.due_at + timedelta(days=1)  # late
            if submitted_at > now:
                submitted_at = now

            sub = Submission(user_id=user.id, week_id=week.id, submitted_at=submitted_at, updated_at=submitted_at)
            session.add(sub)
            session.commit()
            session.refresh(sub)

            for c in courses:
                if drop_after is not None and c is courses[-1] and week.number > drop_after:
                    continue
                base[c.id] = min(100, max(40, base[c.id] + trend + rng.uniform(-3, 3)))
                session.add(ClassGrade(submission_id=sub.id, course_id=c.id, percent=round(base[c.id], 1)))
            session.commit()

    print(f"added {len(SAMPLE_MEMBERS)} sample members (password test123)")
    seed_management(session, weeks, now)


def seed_management(session: Session, weeks: list[Week], now: datetime):
    # a few chair actions so the member page has something to show
    chair = session.exec(select(User).where(User.role == "chair")).first()
    jordan = session.exec(select(User).where(User.email == "jordan@test.com")).first()
    riley = session.exec(select(User).where(User.email == "riley@test.com")).first()
    due = [w for w in weeks if w.due_at < now]
    if chair is None or jordan is None or not due:
        return
    last = due[-1]

    session.add(Note(user_id=jordan.id, week_id=last.id, author_id=chair.id, text="Talked after chapter. Going to PHYS 213 office hours on Tuesdays.", created_at=now, updated_at=now))
    log(session, chair.id, "add_note", jordan.id, week_id=last.id, new_value="Talked after chapter. Going to PHYS 213 office hours on Tuesdays.")

    # fix a typo on an older week
    sub = session.exec(select(Submission).where(Submission.user_id == jordan.id, Submission.week_id == due[2].id)).first()
    if sub is not None:
        grade = session.exec(select(ClassGrade).where(ClassGrade.submission_id == sub.id)).first()
        old = grade.percent
        grade.percent = round(old + 9, 1)
        grade.corrected_at = now
        grade.corrected_by = chair.id
        session.add(grade)
        log(session, chair.id, "correct_grade", jordan.id, week_id=due[2].id, course_id=grade.course_id,
            old_value=fmt_percent(old), new_value=fmt_percent(grade.percent), reason="Typo, checked his Canvas")

    session.add(FlagMute(user_id=jordan.id, week_id=last.id, kind="gpa_below", label="GPA below 2.5", reason="Already meeting weekly about it", muted_by=chair.id))
    log(session, chair.id, "mute_flag", jordan.id, week_id=last.id, detail="GPA below 2.5", reason="Already meeting weekly about it")

    if riley is not None:
        riley.active = False
        session.add(riley)
        log(session, chair.id, "deactivate", riley.id, reason="Transferred schools")

    session.commit()
    print("added a sample note, correction and muted flag for Jordan, and deactivated Riley")


with Session(engine) as session:
    seed_chair(session)
    term = seed_term(session)
    if add_sample:
        seed_sample(session, term)
