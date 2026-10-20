from datetime import date, datetime, timedelta
from typing import Optional

from sqlmodel import Session, select

from grading import calc_gpa, letter_and_points
from models import ClassGrade, ClassResult, Course, FlagMute, FlagOut, FlagRule, GradeScale, Submission, Term, User, Week, WeekResult

# kind, default threshold, on by default
DEFAULT_FLAG_RULES = [
    ("missing", None, True),
    ("late", None, True),
    ("gpa_below", 2.5, True),
    ("class_below", 70.0, True),
    ("gpa_drop", 0.3, True),
    ("class_drop", 10.0, True),
    ("missed_in_row", 2.0, True),
]

FLAG_KINDS = [kind for kind, _, _ in DEFAULT_FLAG_RULES]

# flags that are about one class, muted per class
CLASS_FLAG_KINDS = {"class_below", "class_drop"}


def current_term(session: Session) -> Optional[Term]:
    # the newest term that has started, so setting up next term early does not hide this one
    terms = session.exec(select(Term).order_by(Term.start_date.desc())).all()
    for term in terms:
        if term.start_date <= date.today():
            return term
    # only future terms exist, use the soonest one
    if terms:
        return terms[-1]
    return None


def generate_weeks(term: Term) -> list[Week]:
    weeks = []
    week_start = term.start_date
    number = 1
    while week_start <= term.end_date:
        # due on the first due weekday on or after the week start
        offset = (term.due_weekday - week_start.weekday()) % 7
        due_at = datetime.combine(week_start + timedelta(days=offset), term.due_time)
        weeks.append(Week(term_id=term.id, number=number, start_date=week_start, due_at=due_at))
        week_start = week_start + timedelta(days=7)
        number += 1
    return weeks


def term_weeks(session: Session, term: Term) -> list[Week]:
    return list(session.exec(select(Week).where(Week.term_id == term.id).order_by(Week.number)).all())


def started_weeks(session: Session, term: Term) -> list[Week]:
    today = date.today()
    return [w for w in term_weeks(session, term) if w.start_date <= today]


def week_status(week: Week, submission: Optional[Submission], user: User, now: datetime) -> str:
    if submission is not None:
        if submission.submitted_at <= week.due_at:
            return "on_time"
        return "late"
    # weeks that were due before they joined do not count against them
    if week.due_at < user.created_at:
        return "not_member"
    if now > week.due_at:
        return "missing"
    return "open"


def user_history(
    session: Session,
    user: User,
    weeks: list[Week],
    scale: list[GradeScale],
    rules: Optional[list[FlagRule]] = None,
) -> list[WeekResult]:
    # one entry per week, oldest first, with changes and flags filled in
    now = datetime.now()
    week_ids = [w.id for w in weeks]

    submissions = session.exec(
        select(Submission).where(Submission.user_id == user.id, Submission.week_id.in_(week_ids))
    ).all()
    sub_by_week = {s.week_id: s for s in submissions}

    grades = session.exec(
        select(ClassGrade).where(ClassGrade.submission_id.in_([s.id for s in submissions]))
    ).all()
    grades_by_sub = {}
    for g in grades:
        grades_by_sub.setdefault(g.submission_id, []).append(g)

    courses = session.exec(select(Course).where(Course.user_id == user.id)).all()
    course_by_id = {c.id: c for c in courses}

    results = []
    previous = None
    for week in weeks:
        sub = sub_by_week.get(week.id)
        result = WeekResult(
            week_id=week.id,
            number=week.number,
            due_at=week.due_at,
            status=week_status(week, sub, user, now),
        )

        if sub is not None:
            result.submitted_at = sub.submitted_at
            gpa_entries = []
            for g in grades_by_sub.get(sub.id, []):
                course = course_by_id.get(g.course_id)
                if course is None:
                    continue
                letter, points = letter_and_points(g.percent, g.letter, scale)
                result.classes.append(
                    ClassResult(
                        course_id=course.id,
                        code=course.code,
                        credits=course.credits,
                        percent=g.percent,
                        letter=letter,
                        corrected=g.corrected_at is not None,
                    )
                )
                gpa_entries.append((course.credits, points))
            result.classes.sort(key=lambda c: c.code)
            result.gpa = calc_gpa(gpa_entries)

        # compare to the week right before this one
        if previous is not None and previous.gpa is not None and result.gpa is not None:
            result.gpa_change = round(result.gpa - previous.gpa, 2)
        if previous is not None:
            prev_classes = {c.course_id: c for c in previous.classes}
            for c in result.classes:
                prev = prev_classes.get(c.course_id)
                if prev is not None and prev.percent is not None and c.percent is not None:
                    c.change = round(c.percent - prev.percent, 1)

        results.append(result)
        previous = result

    if rules is not None:
        mutes = session.exec(
            select(FlagMute).where(FlagMute.user_id == user.id, FlagMute.week_id.in_(week_ids))
        ).all()
        mute_by_key = {(m.week_id, m.kind, m.course_id): m for m in mutes}

        for i in range(len(results)):
            results[i].flags = evaluate_flags(results, i, rules)
            for flag in results[i].flags:
                mute = mute_by_key.get((results[i].week_id, flag.kind, flag.course_id))
                if mute is not None:
                    flag.muted = True
                    flag.mute_id = mute.id
                    flag.mute_reason = mute.reason

    return results


def active_flags(flags: list[FlagOut]) -> list[FlagOut]:
    # muted flags stay visible on the member page but do not count anywhere else
    return [f for f in flags if not f.muted]


def fmt(number: float) -> str:
    # 2.50 -> 2.5, 70.0 -> 70
    return f"{number:g}"


def evaluate_flags(history: list[WeekResult], index: int, rules: list[FlagRule]) -> list[FlagOut]:
    week = history[index]
    on = {r.kind: r for r in rules if r.enabled}
    flags = []

    if "missing" in on and week.status == "missing":
        flags.append(FlagOut(kind="missing", label="Missing"))

    if "late" in on and week.status == "late":
        flags.append(FlagOut(kind="late", label="Late"))

    rule = on.get("gpa_below")
    if rule and rule.threshold is not None and week.gpa is not None and week.gpa < rule.threshold:
        flags.append(FlagOut(kind="gpa_below", label=f"GPA below {fmt(rule.threshold)}"))

    rule = on.get("class_below")
    if rule and rule.threshold is not None:
        for c in week.classes:
            if c.percent is not None and c.percent < rule.threshold:
                flags.append(FlagOut(kind="class_below", label=f"{c.code} below {fmt(rule.threshold)}%", course_id=c.course_id))

    rule = on.get("gpa_drop")
    if rule and rule.threshold is not None and week.gpa_change is not None and week.gpa_change <= -rule.threshold:
        flags.append(FlagOut(kind="gpa_drop", label=f"GPA down {fmt(abs(week.gpa_change))}"))

    rule = on.get("class_drop")
    if rule and rule.threshold is not None:
        for c in week.classes:
            if c.change is not None and c.change <= -rule.threshold:
                flags.append(FlagOut(kind="class_drop", label=f"{c.code} down {fmt(abs(c.change))}%", course_id=c.course_id))

    rule = on.get("missed_in_row")
    if rule and rule.threshold is not None and rule.threshold > 0:
        count = 0
        i = index
        while i >= 0 and history[i].status == "missing":
            count += 1
            i -= 1
        if count >= rule.threshold:
            flags.append(FlagOut(kind="missed_in_row", label=f"Missed {count} in a row"))

    return flags
