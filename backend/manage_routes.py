# chair actions on a member: mute flags, correct grades, notes, edit, deactivate, delete
# all of these act on the member as the chair, the chair never logs in as them

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, or_
from sqlmodel import Session, select

from audit import fmt_percent, log
from auth import require_chair
from database import get_session
from grading import load_scale
from models import (
    AuditLog,
    ClassGrade,
    CorrectIn,
    Course,
    DeleteMemberIn,
    FlagMute,
    FlagRule,
    LogEntryOut,
    MemberEditIn,
    MuteIn,
    Note,
    NoteIn,
    NoteOut,
    ReasonIn,
    Screenshot,
    Submission,
    User,
    UserOut,
    Week,
)
from screenshots import delete_file
from tracking import (
    CLASS_FLAG_KINDS,
    FLAG_KINDS,
    current_term,
    started_weeks,
    user_history,
)

router = APIRouter(tags=["chair management"])


def get_member(session: Session, user_id: int) -> User:
    user = session.get(User, user_id)
    # only member accounts can be managed, never the chair
    if user is None or user.role != "member":
        raise HTTPException(status_code=404, detail="Member not found")
    return user


def get_week(session: Session, week_id: int) -> Week:
    week = session.get(Week, week_id)
    if week is None:
        raise HTTPException(status_code=404, detail="Week not found")
    return week


# mute flags

@router.post("/members/{user_id}/weeks/{week_id}/mutes", response_model=FlagMute)
def mute_flag(
    user_id: int,
    week_id: int,
    data: MuteIn,
    chair: User = Depends(require_chair),
    session: Session = Depends(get_session),
):
    member = get_member(session, user_id)
    week = get_week(session, week_id)

    if data.kind not in FLAG_KINDS:
        raise HTTPException(status_code=400, detail=f"Unknown flag type {data.kind}")
    # class flags are muted per class, the rest have no class
    if data.kind in CLASS_FLAG_KINDS and data.course_id is None:
        raise HTTPException(status_code=400, detail="Pick which class's flag to mute")
    if data.kind not in CLASS_FLAG_KINDS and data.course_id is not None:
        raise HTTPException(status_code=400, detail="That flag isn't for a single class")

    # only flags that are showing right now can be muted, so nothing gets muted ahead of time
    term = current_term(session)
    weeks = []
    if term is not None:
        weeks = [w for w in started_weeks(session, term) if w.number <= week.number]
    if not weeks or weeks[-1].id != week.id:
        raise HTTPException(status_code=400, detail="You can only mute flags on weeks of the current term that have started")

    rules = list(session.exec(select(FlagRule)).all())
    current = user_history(session, member, weeks, load_scale(session), rules)[-1]
    match = [f for f in current.flags if f.kind == data.kind and f.course_id == data.course_id]
    if not match:
        raise HTTPException(status_code=400, detail="That flag isn't showing for this week")
    if match[0].muted:
        raise HTTPException(status_code=400, detail="That flag is already muted")

    mute = FlagMute(
        user_id=member.id,
        week_id=week.id,
        kind=data.kind,
        course_id=data.course_id,
        label=match[0].label,
        reason=data.reason.strip(),
        muted_by=chair.id,
    )
    session.add(mute)
    log(session, chair.id, "mute_flag", member.id, week_id=week.id, course_id=data.course_id, detail=mute.label, reason=mute.reason)
    session.commit()
    session.refresh(mute)
    return mute


@router.delete("/mutes/{mute_id}")
def unmute_flag(mute_id: int, chair: User = Depends(require_chair), session: Session = Depends(get_session)):
    mute = session.get(FlagMute, mute_id)
    if mute is None:
        raise HTTPException(status_code=404, detail="Mute not found")
    log(session, chair.id, "unmute_flag", mute.user_id, week_id=mute.week_id, course_id=mute.course_id, detail=mute.label)
    session.delete(mute)
    session.commit()
    return {"message": f"Unmuted {mute.label}"}


# correct a grade

@router.put("/members/{user_id}/weeks/{week_id}/grades/{course_id}")
def correct_grade(
    user_id: int,
    week_id: int,
    course_id: int,
    data: CorrectIn,
    chair: User = Depends(require_chair),
    session: Session = Depends(get_session),
):
    member = get_member(session, user_id)
    week = get_week(session, week_id)

    sub = session.exec(select(Submission).where(Submission.user_id == member.id, Submission.week_id == week.id)).first()
    if sub is None:
        raise HTTPException(status_code=400, detail="There's no submission for that week. The member has to submit it first.")

    grade = session.exec(
        select(ClassGrade).where(ClassGrade.submission_id == sub.id, ClassGrade.course_id == course_id)
    ).first()
    if grade is None:
        raise HTTPException(status_code=404, detail="That class isn't in this week's submission")
    if grade.percent == data.percent:
        raise HTTPException(status_code=400, detail="That's already the grade")

    old = grade.percent
    grade.percent = data.percent
    grade.corrected_at = datetime.now()
    grade.corrected_by = chair.id
    session.add(grade)
    log(
        session,
        chair.id,
        "correct_grade",
        member.id,
        week_id=week.id,
        course_id=course_id,
        old_value=fmt_percent(old),
        new_value=fmt_percent(data.percent),
        reason=data.reason.strip(),
    )
    session.commit()

    course = session.get(Course, course_id)
    return {"message": f"Corrected {course.code} for week {week.number} to {data.percent:g}%"}


# notes

def note_out(session: Session, note: Note) -> NoteOut:
    week_number = None
    if note.week_id is not None:
        week = session.get(Week, note.week_id)
        if week is not None:
            week_number = week.number
    author = session.get(User, note.author_id)
    author_name = "Deleted user"
    if author is not None:
        author_name = author.name
    return NoteOut(
        id=note.id,
        week_id=note.week_id,
        week_number=week_number,
        author_name=author_name,
        text=note.text,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


def short(text: str) -> str:
    # keep log rows readable
    if len(text) > 200:
        return text[:197] + "..."
    return text


def clean_note(session: Session, data: NoteIn) -> str:
    text = data.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="The note is empty")
    if data.week_id is not None:
        get_week(session, data.week_id)
    return text


@router.get("/members/{user_id}/notes", response_model=list[NoteOut])
def list_notes(user_id: int, chair: User = Depends(require_chair), session: Session = Depends(get_session)):
    member = get_member(session, user_id)
    notes = session.exec(select(Note).where(Note.user_id == member.id).order_by(Note.created_at.desc())).all()
    return [note_out(session, n) for n in notes]


@router.post("/members/{user_id}/notes", response_model=NoteOut)
def add_note(user_id: int, data: NoteIn, chair: User = Depends(require_chair), session: Session = Depends(get_session)):
    member = get_member(session, user_id)
    text = clean_note(session, data)
    now = datetime.now()
    # same time for both so the page can tell an edited note apart
    note = Note(user_id=member.id, week_id=data.week_id, author_id=chair.id, text=text, created_at=now, updated_at=now)
    session.add(note)
    log(session, chair.id, "add_note", member.id, week_id=data.week_id, new_value=short(text))
    session.commit()
    session.refresh(note)
    return note_out(session, note)


@router.put("/notes/{note_id}", response_model=NoteOut)
def edit_note(note_id: int, data: NoteIn, chair: User = Depends(require_chair), session: Session = Depends(get_session)):
    note = session.get(Note, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    text = clean_note(session, data)
    log(session, chair.id, "edit_note", note.user_id, week_id=data.week_id, old_value=short(note.text), new_value=short(text))
    note.text = text
    note.week_id = data.week_id
    note.updated_at = datetime.now()
    session.add(note)
    session.commit()
    session.refresh(note)
    return note_out(session, note)


@router.delete("/notes/{note_id}")
def delete_note(note_id: int, chair: User = Depends(require_chair), session: Session = Depends(get_session)):
    note = session.get(Note, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    log(session, chair.id, "delete_note", note.user_id, week_id=note.week_id, old_value=short(note.text))
    session.delete(note)
    session.commit()
    return {"message": "Note deleted"}


# edit, deactivate, delete

@router.patch("/members/{user_id}", response_model=UserOut)
def edit_member(user_id: int, data: MemberEditIn, chair: User = Depends(require_chair), session: Session = Depends(get_session)):
    member = get_member(session, user_id)

    changes = {}
    if data.name is not None:
        name = data.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name can't be blank")
        changes["name"] = name
    if data.pledge_class is not None:
        changes["pledge_class"] = data.pledge_class.strip()

    for field, value in changes.items():
        old = getattr(member, field)
        if old != value:
            log(session, chair.id, "edit_member", member.id, detail=field, old_value=old, new_value=value)
            setattr(member, field, value)

    session.add(member)
    session.commit()
    session.refresh(member)
    return member


@router.post("/members/{user_id}/deactivate", response_model=UserOut)
def deactivate_member(user_id: int, data: ReasonIn, chair: User = Depends(require_chair), session: Session = Depends(get_session)):
    member = get_member(session, user_id)
    if not member.active:
        raise HTTPException(status_code=400, detail="That member is already inactive")
    member.active = False
    session.add(member)
    log(session, chair.id, "deactivate", member.id, reason=data.reason.strip())
    session.commit()
    session.refresh(member)
    return member


@router.post("/members/{user_id}/reactivate", response_model=UserOut)
def reactivate_member(user_id: int, data: ReasonIn, chair: User = Depends(require_chair), session: Session = Depends(get_session)):
    member = get_member(session, user_id)
    if member.active:
        raise HTTPException(status_code=400, detail="That member is already active")
    member.active = True
    session.add(member)
    log(session, chair.id, "reactivate", member.id, reason=data.reason.strip())
    session.commit()
    session.refresh(member)
    return member


@router.delete("/members/{user_id}")
def delete_member(user_id: int, data: DeleteMemberIn, chair: User = Depends(require_chair), session: Session = Depends(get_session)):
    member = get_member(session, user_id)
    # typing the name is the confirmation, checked here too so the api can't skip it
    if data.confirm_name.strip() != member.name:
        raise HTTPException(status_code=400, detail="The name you typed doesn't match. Nothing was deleted.")

    course_ids = list(session.exec(select(Course.id).where(Course.user_id == member.id)).all())
    sub_ids = list(session.exec(select(Submission.id).where(Submission.user_id == member.id)).all())
    image_files = list(session.exec(select(Screenshot.file_name).where(Screenshot.submission_id.in_(sub_ids))).all())

    # children first so foreign keys are never left pointing at nothing
    session.execute(
        delete(AuditLog).where(
            or_(
                AuditLog.target_user_id == member.id,
                AuditLog.actor_id == member.id,
                AuditLog.course_id.in_(course_ids),
            )
        )
    )
    session.execute(delete(FlagMute).where(FlagMute.user_id == member.id))
    session.execute(delete(Note).where(Note.user_id == member.id))
    session.execute(delete(ClassGrade).where(ClassGrade.submission_id.in_(sub_ids)))
    session.execute(delete(Screenshot).where(Screenshot.submission_id.in_(sub_ids)))
    session.execute(delete(Submission).where(Submission.user_id == member.id))
    session.execute(delete(Course).where(Course.user_id == member.id))
    session.delete(member)

    # one row is kept so the chair can see a delete happened, without who it was
    log(session, chair.id, "delete_member", None, reason=data.reason.strip())
    session.commit()

    # the image files go once the rows are gone
    for name in image_files:
        delete_file(name)
    return {"message": "Member and all their data were deleted"}


# change log

@router.get("/members/{user_id}/log", response_model=list[LogEntryOut])
def member_log(user_id: int, chair: User = Depends(require_chair), session: Session = Depends(get_session)):
    member = get_member(session, user_id)
    rows = session.exec(
        select(AuditLog).where(AuditLog.target_user_id == member.id).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    ).all()

    # look up names once instead of per row
    user_ids = {r.actor_id for r in rows if r.actor_id is not None}
    names = {u.id: u.name for u in session.exec(select(User).where(User.id.in_(user_ids))).all()}
    week_ids = {r.week_id for r in rows if r.week_id is not None}
    weeks = {w.id: w.number for w in session.exec(select(Week).where(Week.id.in_(week_ids))).all()}
    course_ids = {r.course_id for r in rows if r.course_id is not None}
    codes = {c.id: c.code for c in session.exec(select(Course).where(Course.id.in_(course_ids))).all()}

    out = []
    for r in rows:
        out.append(
            LogEntryOut(
                id=r.id,
                actor_name=names.get(r.actor_id, "Deleted user"),
                action=r.action,
                week_number=weeks.get(r.week_id),
                course_code=codes.get(r.course_id),
                detail=r.detail,
                old_value=r.old_value,
                new_value=r.new_value,
                reason=r.reason,
                created_at=r.created_at,
            )
        )
    return out
