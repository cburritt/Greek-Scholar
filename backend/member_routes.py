from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from audit import fmt_percent, log
from auth import require_member
from database import get_session
from grading import load_scale
from models import ClassGrade, Course, CourseIn, HistoryOut, Submission, SubmissionIn, User, UserOut, Week
from tracking import current_term, started_weeks, user_history

router = APIRouter(tags=["member"])


def require_term(session: Session):
    term = current_term(session)
    if term is None:
        raise HTTPException(status_code=400, detail="The chair has not set up a term yet")
    return term


# classes

@router.get("/courses", response_model=list[Course])
def list_courses(include_dropped: bool = False, user: User = Depends(require_member), session: Session = Depends(get_session)):
    term = require_term(session)
    query = select(Course).where(Course.user_id == user.id, Course.term_id == term.id)
    if not include_dropped:
        query = query.where(Course.dropped_at.is_(None))
    return session.exec(query.order_by(Course.code)).all()


@router.post("/courses", response_model=Course)
def add_course(data: CourseIn, user: User = Depends(require_member), session: Session = Depends(get_session)):
    term = require_term(session)
    code = data.code.strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="Class code can't be blank")

    same = session.exec(
        select(Course).where(
            Course.user_id == user.id,
            Course.term_id == term.id,
            Course.code == code,
            Course.dropped_at.is_(None),
        )
    ).first()
    if same:
        raise HTTPException(status_code=400, detail=f"You already have {code}")

    course = Course(user_id=user.id, term_id=term.id, code=code, name=data.name.strip(), credits=data.credits)
    session.add(course)
    session.commit()
    session.refresh(course)
    return course


@router.delete("/courses/{course_id}")
def drop_course(course_id: int, user: User = Depends(require_member), session: Session = Depends(get_session)):
    course = session.get(Course, course_id)
    if course is None or course.user_id != user.id:
        raise HTTPException(status_code=404, detail="Class not found")
    if course.dropped_at is not None:
        raise HTTPException(status_code=400, detail=f"{course.code} is already dropped")

    # keep the row so past weeks still show it
    course.dropped_at = datetime.now()
    session.add(course)
    session.commit()
    return {"message": f"Dropped {course.code}"}


# weekly submissions

def classes_for_week(session: Session, user: User, term_id: int, week: Week) -> list[Course]:
    # current classes, plus any class dropped after this week was already due
    courses = session.exec(select(Course).where(Course.user_id == user.id, Course.term_id == term_id)).all()
    return [c for c in courses if c.dropped_at is None or c.dropped_at > week.due_at]


@router.get("/weeks/{week_id}/courses", response_model=list[Course])
def week_courses(week_id: int, user: User = Depends(require_member), session: Session = Depends(get_session)):
    term = require_term(session)
    week = session.get(Week, week_id)
    if week is None or week.term_id != term.id:
        raise HTTPException(status_code=404, detail="Week not found")
    return sorted(classes_for_week(session, user, term.id, week), key=lambda c: c.code)


@router.post("/submissions")
def submit_week(data: SubmissionIn, user: User = Depends(require_member), session: Session = Depends(get_session)):
    term = require_term(session)

    week = session.get(Week, data.week_id)
    if week is None or week.term_id != term.id:
        raise HTTPException(status_code=404, detail="Week not found")
    if week.start_date > date.today():
        raise HTTPException(status_code=400, detail="That week has not started yet")

    # a past week uses the classes they had that week, so a dropped class keeps its old grades
    active = classes_for_week(session, user, term.id, week)
    if not active:
        raise HTTPException(status_code=400, detail="Add your classes before submitting grades")

    active_ids = {c.id for c in active}
    sent_ids = [g.course_id for g in data.grades]
    if len(sent_ids) != len(set(sent_ids)):
        raise HTTPException(status_code=400, detail="A class was listed twice")
    if set(sent_ids) != active_ids:
        raise HTTPException(status_code=400, detail="Enter a grade for every one of your classes")

    sub = session.exec(
        select(Submission).where(Submission.user_id == user.id, Submission.week_id == week.id)
    ).first()

    # resubmitting replaces the grades but keeps the first submit time for late
    old_percent = {}
    if sub is None:
        sub = Submission(user_id=user.id, week_id=week.id)
        session.add(sub)
        # flush gets the id without saving, so a failure below saves nothing
        session.flush()
    else:
        sub.updated_at = datetime.now()
        session.add(sub)
        old = session.exec(select(ClassGrade).where(ClassGrade.submission_id == sub.id)).all()
        for g in old:
            old_percent[g.course_id] = g.percent
            session.delete(g)

        # log every grade that changed so chair corrections can't quietly disappear
        new_percent = {g.course_id: g.percent for g in data.grades}
        for course_id in sorted(set(old_percent) | set(new_percent)):
            before = old_percent.get(course_id)
            after = new_percent.get(course_id)
            if before != after:
                log(
                    session,
                    user.id,
                    "resubmit_grade",
                    user.id,
                    week_id=week.id,
                    course_id=course_id,
                    old_value=fmt_percent(before),
                    new_value=fmt_percent(after),
                )

    for g in data.grades:
        session.add(ClassGrade(submission_id=sub.id, course_id=g.course_id, percent=g.percent))
    session.commit()

    late = sub.submitted_at > week.due_at
    message = f"Grades submitted for week {week.number}"
    if late:
        message += " (late)"
    return {"message": message, "late": late}


@router.get("/submissions/me", response_model=HistoryOut)
def my_history(user: User = Depends(require_member), session: Session = Depends(get_session)):
    term = require_term(session)
    weeks = started_weeks(session, term)
    courses = session.exec(select(Course).where(Course.user_id == user.id, Course.term_id == term.id)).all()
    # members see their own grades but not the chair's flags
    history = user_history(session, user, weeks, load_scale(session))
    return HistoryOut(user=UserOut.model_validate(user), courses=courses, weeks=history)
