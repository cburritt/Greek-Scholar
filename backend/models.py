from datetime import date, datetime, time
from typing import Optional

from pydantic import NaiveDatetime
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


class TermIn(SQLModel):
    name: str = Field(min_length=1)
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
    code: str = Field(min_length=1)
    name: str = ""
    credits: int = Field(gt=0, le=12)


class GradeEntry(SQLModel):
    course_id: int
    percent: float = Field(ge=0, le=120)


class SubmissionIn(SQLModel):
    week_id: int
    grades: list[GradeEntry] = Field(min_length=1)


class ClassResult(SQLModel):
    course_id: int
    code: str
    credits: int
    percent: Optional[float] = None
    letter: Optional[str] = None
    change: Optional[float] = None


class FlagOut(SQLModel):
    kind: str
    label: str


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
