from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from auth import require_chair
from database import get_session
from grading import load_scale
from models import (
    Course,
    FlagRule,
    FlagRuleIn,
    GradeScale,
    GradeScaleIn,
    HistoryOut,
    MemberRow,
    Term,
    TermIn,
    User,
    UserOut,
    WeekStat,
)
from tracking import (
    FLAG_KINDS,
    active_flags,
    current_term,
    generate_weeks,
    started_weeks,
    user_history,
)

router = APIRouter(tags=["chair"])


def load_rules(session: Session) -> list[FlagRule]:
    return list(session.exec(select(FlagRule)).all())


def all_members(session: Session, pledge_class: Optional[str] = None, include_inactive: bool = False) -> list[User]:
    query = select(User).where(User.role == "member")
    if not include_inactive:
        query = query.where(User.active.is_(True))
    if pledge_class:
        query = query.where(User.pledge_class == pledge_class)
    return list(session.exec(query).all())


# terms

@router.get("/terms", response_model=list[Term])
def list_terms(chair: User = Depends(require_chair), session: Session = Depends(get_session)):
    return session.exec(select(Term).order_by(Term.start_date.desc())).all()


@router.post("/terms", response_model=Term)
def create_term(data: TermIn, chair: User = Depends(require_chair), session: Session = Depends(get_session)):
    if data.end_date <= data.start_date:
        raise HTTPException(status_code=400, detail="End date must be after the start date")
    # a typo in the year would otherwise make thousands of weeks
    if (data.end_date - data.start_date).days > 366:
        raise HTTPException(status_code=400, detail="A term can't be longer than a year")
    if not data.name.strip():
        raise HTTPException(status_code=400, detail="Term name can't be blank")

    term = Term.model_validate(data)
    term.name = term.name.strip()
    session.add(term)
    # flush gets the id, the term and its weeks are saved together below
    session.flush()

    # make every week of the term up front
    for week in generate_weeks(term):
        session.add(week)
    session.commit()
    session.refresh(term)
    return term


# members table

@router.get("/pledge-classes", response_model=list[str])
def pledge_classes(chair: User = Depends(require_chair), session: Session = Depends(get_session)):
    classes = {u.pledge_class for u in all_members(session) if u.pledge_class}
    return sorted(classes)


@router.get("/members", response_model=list[MemberRow])
def members(
    week_id: Optional[int] = None,
    pledge_class: Optional[str] = None,
    status: Optional[Literal["on_time", "late", "missing", "open", "submitted"]] = None,
    flag: Optional[str] = None,
    sort: Literal["name", "gpa", "change"] = "name",
    include_inactive: bool = False,
    chair: User = Depends(require_chair),
    session: Session = Depends(get_session),
):
    term = current_term(session)
    if term is None:
        return []
    weeks = started_weeks(session, term)
    if not weeks:
        return []

    # default to the newest week, and only look at weeks up to the chosen one
    selected = weeks[-1]
    if week_id is not None:
        match = [w for w in weeks if w.id == week_id]
        if not match:
            raise HTTPException(status_code=404, detail="Week not found")
        selected = match[0]
    weeks = [w for w in weeks if w.number <= selected.number]

    scale = load_scale(session)
    rules = load_rules(session)

    rows = []
    for u in all_members(session, pledge_class, include_inactive):
        week = user_history(session, u, weeks, scale, rules)[-1]
        rows.append(
            MemberRow(
                user_id=u.id,
                name=u.name,
                email=u.email,
                pledge_class=u.pledge_class,
                active=u.active,
                status=week.status,
                submitted_at=week.submitted_at,
                gpa=week.gpa,
                gpa_change=week.gpa_change,
                classes=week.classes,
                flags=week.flags,
                screenshot_id=week.screenshot_id,
            )
        )

    if status == "submitted":
        rows = [r for r in rows if r.status in ("on_time", "late")]
    elif status is not None:
        rows = [r for r in rows if r.status == status]

    # muted flags never count for the filters
    if flag == "any":
        rows = [r for r in rows if active_flags(r.flags)]
    elif flag:
        rows = [r for r in rows if any(f.kind == flag for f in active_flags(r.flags))]

    if sort == "gpa":
        # lowest first, no gpa at the bottom
        rows.sort(key=lambda r: (r.gpa is None, r.gpa or 0))
    elif sort == "change":
        # biggest drop first
        rows.sort(key=lambda r: (r.gpa_change is None, r.gpa_change or 0))
    else:
        rows.sort(key=lambda r: r.name.lower())

    return rows


@router.get("/members/{user_id}/history", response_model=HistoryOut)
def member_history(user_id: int, chair: User = Depends(require_chair), session: Session = Depends(get_session)):
    user = session.get(User, user_id)
    if user is None or user.role != "member":
        raise HTTPException(status_code=404, detail="Member not found")

    term = current_term(session)
    if term is None:
        return HistoryOut(user=UserOut.model_validate(user), courses=[], weeks=[])

    weeks = started_weeks(session, term)
    courses = session.exec(select(Course).where(Course.user_id == user.id, Course.term_id == term.id)).all()
    history = user_history(session, user, weeks, load_scale(session), load_rules(session))
    return HistoryOut(user=UserOut.model_validate(user), courses=courses, weeks=history)


@router.get("/stats/weekly", response_model=list[WeekStat])
def weekly_stats(chair: User = Depends(require_chair), session: Session = Depends(get_session)):
    term = current_term(session)
    if term is None:
        return []
    weeks = started_weeks(session, term)
    scale = load_scale(session)
    histories = [user_history(session, u, weeks, scale) for u in all_members(session)]

    stats = []
    for i, week in enumerate(weeks):
        gpas = []
        counts = {"on_time": 0, "late": 0, "missing": 0, "open": 0, "not_member": 0}
        for history in histories:
            entry = history[i]
            counts[entry.status] += 1
            if entry.gpa is not None:
                gpas.append(entry.gpa)

        avg = None
        if gpas:
            avg = round(sum(gpas) / len(gpas), 2)

        stats.append(
            WeekStat(
                week_id=week.id,
                number=week.number,
                due_at=week.due_at,
                avg_gpa=avg,
                on_time=counts["on_time"],
                late=counts["late"],
                missing=counts["missing"],
                expected=len(histories) - counts["not_member"],
            )
        )
    return stats


# settings

@router.get("/settings/flags", response_model=list[FlagRule])
def get_flags(chair: User = Depends(require_chair), session: Session = Depends(get_session)):
    rules = {r.kind: r for r in load_rules(session)}
    # keep a stable order for the settings page
    return [rules[k] for k in FLAG_KINDS if k in rules]


@router.put("/settings/flags", response_model=list[FlagRule])
def update_flags(data: list[FlagRuleIn], chair: User = Depends(require_chair), session: Session = Depends(get_session)):
    rules = {r.kind: r for r in load_rules(session)}
    for item in data:
        rule = rules.get(item.kind)
        if rule is None:
            raise HTTPException(status_code=400, detail=f"Unknown flag type {item.kind}")
        if item.threshold is not None and item.threshold < 0:
            raise HTTPException(status_code=400, detail="Thresholds cannot be negative")
        rule.enabled = item.enabled
        # missing and late have no number
        if rule.threshold is not None:
            if item.threshold is None:
                raise HTTPException(status_code=400, detail=f"{item.kind} needs a number")
            rule.threshold = item.threshold
        session.add(rule)
    session.commit()
    return get_flags(chair, session)


@router.put("/settings/grade-scale", response_model=list[GradeScale])
def update_grade_scale(data: list[GradeScaleIn], chair: User = Depends(require_chair), session: Session = Depends(get_session)):
    if not data:
        raise HTTPException(status_code=400, detail="The scale needs at least one row")
    letters = [row.letter.strip().upper() for row in data]
    if "" in letters:
        raise HTTPException(status_code=400, detail="Every row needs a letter")
    if len(letters) != len(set(letters)):
        raise HTTPException(status_code=400, detail="Each letter can only be listed once")
    if not any(row.min_percent == 0 for row in data):
        raise HTTPException(status_code=400, detail="One row needs a minimum of 0 so every grade gets a letter")
    mins = [row.min_percent for row in data]
    if len(mins) != len(set(mins)):
        raise HTTPException(status_code=400, detail="Each minimum % can only be used once")
    # a higher cutoff should never be worth fewer points
    ordered = sorted(data, key=lambda r: r.min_percent, reverse=True)
    for higher, lower in zip(ordered, ordered[1:], strict=False):
        if lower.points > higher.points:
            raise HTTPException(status_code=400, detail=f"{lower.letter} is worth more points than {higher.letter} but has a lower minimum")

    # replace the whole scale
    for row in session.exec(select(GradeScale)).all():
        session.delete(row)
    for row, letter in zip(data, letters, strict=True):
        session.add(GradeScale(letter=letter, min_percent=row.min_percent, points=row.points))
    session.commit()
    return load_scale(session)
