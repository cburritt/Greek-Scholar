import re
from datetime import date, datetime, time
from typing import Optional

from pydantic import NaiveDatetime, field_validator
from sqlmodel import Field, SQLModel, UniqueConstraint


# tables

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    email: str = Field(unique=True, index=True)
    password_hash: str
    role: str = "member"  # member or chair
    pledge_class: str = ""
    created_at: NaiveDatetime = Field(default_factory=datetime.now)
    # deactivated members cannot log in and are hidden from the chair views
    active: bool = True


class Term(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    start_date: date
    end_date: date
    due_weekday: int  # 0 = monday, 6 = sunday
    due_time: time


class Week(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    term_id: int = Field(foreign_key="term.id", index=True)
    number: int
    start_date: date
    due_at: NaiveDatetime


class Course(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    term_id: int = Field(foreign_key="term.id")
    code: str
    name: str = ""
    credits: int
    created_at: NaiveDatetime = Field(default_factory=datetime.now)
    # dropped classes are kept so old weeks still show them
    dropped_at: Optional[NaiveDatetime] = None


class Submission(SQLModel, table=True):
    # one submission per member per week
    __table_args__ = (UniqueConstraint("user_id", "week_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    week_id: int = Field(foreign_key="week.id")
    # first time they submitted, used for late
    submitted_at: NaiveDatetime = Field(default_factory=datetime.now)
    updated_at: NaiveDatetime = Field(default_factory=datetime.now)


class ClassGrade(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    submission_id: int = Field(foreign_key="submission.id", index=True)
    course_id: int = Field(foreign_key="course.id")
    # percent schools fill percent, letter schools would fill letter
    percent: Optional[float] = None
    letter: Optional[str] = None
    # set when the chair corrects this grade, cleared when the member resubmits
    corrected_at: Optional[NaiveDatetime] = None
    corrected_by: Optional[int] = Field(default=None, foreign_key="user.id")


class GradeScale(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    letter: str
    min_percent: float
    points: float


class FlagRule(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    kind: str = Field(unique=True)
    threshold: Optional[float] = None
    enabled: bool = True


class HouseSettings(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    # percent for now, letter later
    grade_entry: str = "percent"


class FlagMute(SQLModel, table=True):
    # one mute per flag per member per week, course_id is only for class flags
    __table_args__ = (UniqueConstraint("user_id", "week_id", "kind", "course_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    week_id: int = Field(foreign_key="week.id")
    kind: str
    course_id: Optional[int] = Field(default=None, foreign_key="course.id")
    # the flag text when it was muted, e.g. "PHYS 213 below 70%"
    label: str = ""
    reason: str
    muted_by: int = Field(foreign_key="user.id")
    created_at: NaiveDatetime = Field(default_factory=datetime.now)


class Note(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    week_id: Optional[int] = Field(default=None, foreign_key="week.id")
    author_id: int = Field(foreign_key="user.id")
    text: str
    created_at: NaiveDatetime = Field(default_factory=datetime.now)
    updated_at: NaiveDatetime = Field(default_factory=datetime.now)


class AuditLog(SQLModel, table=True):
    # rows are only ever added, never edited
    id: Optional[int] = Field(default=None, primary_key=True)
    actor_id: Optional[int] = Field(default=None, foreign_key="user.id")
    action: str
    target_user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    week_id: Optional[int] = Field(default=None, foreign_key="week.id")
    course_id: Optional[int] = Field(default=None, foreign_key="course.id")
    detail: str = ""
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    reason: str = ""
    created_at: NaiveDatetime = Field(default_factory=datetime.now)


# request and response shapes

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def check_password(password: str) -> str:
    # bcrypt only reads the first 72 bytes and newer versions reject longer ones
    if len(password.encode()) > 72:
        raise ValueError("Password is too long (72 bytes max)")
    return password


class RegisterIn(SQLModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8)
    pledge_class: str = Field(max_length=40)

    @field_validator("password")
    @classmethod
    def password_length(cls, value):
        return check_password(value)

    @field_validator("email")
    @classmethod
    def email_shape(cls, value):
        # something@something.something, real checking would need a confirmation email
        if not EMAIL_RE.match(value.strip()):
            raise ValueError("Enter a valid email address")
        return value


class UserOut(SQLModel):
    id: int
    name: str
    email: str
    role: str
    pledge_class: str
    active: bool = True


class TokenOut(SQLModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class TermIn(SQLModel):
    name: str = Field(min_length=1, max_length=40)
    start_date: date
    end_date: date
    due_weekday: int = Field(ge=0, le=6)
    due_time: time


class WeekOut(SQLModel):
    id: int
    number: int
    start_date: date
    due_at: NaiveDatetime
    # only filled in for members
    status: Optional[str] = None


class CourseIn(SQLModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(default="", max_length=100)
    credits: int = Field(gt=0, le=12)


class GradeEntry(SQLModel):
    course_id: int
    percent: float = Field(ge=0, le=120)


class SubmissionIn(SQLModel):
    week_id: int
    grades: list[GradeEntry] = Field(min_length=1, max_length=20)


class ClassResult(SQLModel):
    course_id: int
    code: str
    credits: int
    percent: Optional[float] = None
    letter: Optional[str] = None
    change: Optional[float] = None
    corrected: bool = False


class FlagOut(SQLModel):
    kind: str
    label: str
    course_id: Optional[int] = None
    muted: bool = False
    mute_id: Optional[int] = None
    mute_reason: Optional[str] = None


class WeekResult(SQLModel):
    week_id: int
    number: int
    due_at: NaiveDatetime
    status: str  # on_time, late, missing, open, not_member
    submitted_at: Optional[NaiveDatetime] = None
    gpa: Optional[float] = None
    gpa_change: Optional[float] = None
    classes: list[ClassResult] = []
    flags: list[FlagOut] = []


class MemberRow(SQLModel):
    user_id: int
    name: str
    email: str
    pledge_class: str
    active: bool
    status: str
    submitted_at: Optional[NaiveDatetime] = None
    gpa: Optional[float] = None
    gpa_change: Optional[float] = None
    classes: list[ClassResult] = []
    flags: list[FlagOut] = []


class HistoryOut(SQLModel):
    user: UserOut
    courses: list[Course]
    weeks: list[WeekResult]


class WeekStat(SQLModel):
    week_id: int
    number: int
    due_at: NaiveDatetime
    avg_gpa: Optional[float] = None
    on_time: int
    late: int
    missing: int
    expected: int


class FlagRuleIn(SQLModel):
    kind: str
    threshold: Optional[float] = None
    enabled: bool


class GradeScaleIn(SQLModel):
    letter: str = Field(min_length=1, max_length=3)
    min_percent: float = Field(ge=0, le=120)
    points: float = Field(ge=0, le=5)


# chair management

class MuteIn(SQLModel):
    kind: str
    course_id: Optional[int] = None
    reason: str = Field(min_length=1, max_length=500)


class CorrectIn(SQLModel):
    percent: float = Field(ge=0, le=120)
    reason: str = Field(min_length=1, max_length=500)


class NoteIn(SQLModel):
    text: str = Field(min_length=1, max_length=2000)
    week_id: Optional[int] = None


class NoteOut(SQLModel):
    id: int
    week_id: Optional[int] = None
    week_number: Optional[int] = None
    author_name: str
    text: str
    created_at: NaiveDatetime
    updated_at: NaiveDatetime


class MemberEditIn(SQLModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    pledge_class: Optional[str] = Field(default=None, max_length=40)


class ReasonIn(SQLModel):
    reason: str = Field(min_length=1, max_length=500)


class DeleteMemberIn(SQLModel):
    confirm_name: str
    reason: str = Field(min_length=1, max_length=500)


class LogEntryOut(SQLModel):
    id: int
    actor_name: str
    action: str
    week_number: Optional[int] = None
    course_code: Optional[str] = None
    detail: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    reason: str
    created_at: NaiveDatetime
