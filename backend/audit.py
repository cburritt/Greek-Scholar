from typing import Optional

from sqlmodel import Session

from models import AuditLog


def fmt_percent(value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    return f"{value:g}%"


def log(
    session: Session,
    actor_id: Optional[int],
    action: str,
    target_user_id: Optional[int],
    week_id: Optional[int] = None,
    course_id: Optional[int] = None,
    detail: str = "",
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
    reason: str = "",
):
    # added to the session, saved with whatever change it belongs to
    session.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            target_user_id=target_user_id,
            week_id=week_id,
            course_id=course_id,
            detail=detail,
            old_value=old_value,
            new_value=new_value,
            reason=reason,
        )
    )
