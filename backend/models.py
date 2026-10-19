from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint


# tables

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    email: str = Field(unique=True, index=True)
    password_hash: str
    role: str = "member"  # member or chair
    pledge_class: str = ""


class GradeSubmission(SQLModel, table=True):
    # one submission per member per term
    __table_args__ = (UniqueConstraint("user_id", "term"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    term: str
    gpa: float
    credit_hours: int
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# request and response shapes

class RegisterIn(SQLModel):
    name: str = Field(min_length=1)
    email: str = Field(min_length=3)
    password: str = Field(min_length=6)
    pledge_class: str


class UserOut(SQLModel):
    id: int
    name: str
    email: str
    role: str
    pledge_class: str


class TokenOut(SQLModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class GradeIn(SQLModel):
    term: str = Field(min_length=1)
    gpa: float = Field(ge=0, le=4)
    credit_hours: int = Field(gt=0)


class MemberRow(SQLModel):
    name: str
    email: str
    pledge_class: str
    term: str
    gpa: Optional[float] = None
    credit_hours: Optional[int] = None
    submitted_at: Optional[datetime] = None
