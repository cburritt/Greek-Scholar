from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select

from auth import create_token, get_current_user, hash_password, require_chair, require_member, verify_password
from database import create_db, get_session
from models import GradeIn, GradeSubmission, MemberRow, RegisterIn, TokenOut, User, UserOut


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db()
    yield


app = FastAPI(title="Greek Scholar API", lifespan=lifespan)

# let the frontend dev server call the api
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5500", "http://127.0.0.1:5500"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def token_for(user: User) -> TokenOut:
    return TokenOut(access_token=create_token(user.id), user=UserOut.model_validate(user))


@app.post("/register", response_model=TokenOut)
def register(data: RegisterIn, session: Session = Depends(get_session)):
    email = data.email.strip().lower()
    existing = session.exec(select(User).where(User.email == email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with that email already exists")

    # everyone who registers is a member
    user = User(
        name=data.name.strip(),
        email=email,
        password_hash=hash_password(data.password),
        role="member",
        pledge_class=data.pledge_class,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return token_for(user)


@app.post("/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)):
    # the form calls it username but it is the email
    email = form.username.strip().lower()
    user = session.exec(select(User).where(User.email == email)).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Wrong email or password")
    return token_for(user)


@app.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@app.post("/grades")
def submit_grade(data: GradeIn, user: User = Depends(require_member), session: Session = Depends(get_session)):
    term = data.term.strip()
    grade = session.exec(
        select(GradeSubmission).where(GradeSubmission.user_id == user.id, GradeSubmission.term == term)
    ).first()

    # resubmitting for the same term replaces the old one
    if grade is None:
        grade = GradeSubmission(user_id=user.id, term=term, gpa=data.gpa, credit_hours=data.credit_hours)
    else:
        grade.gpa = data.gpa
        grade.credit_hours = data.credit_hours
        grade.submitted_at = datetime.now(timezone.utc)

    session.add(grade)
    session.commit()
    return {"message": f"Grades submitted for {term}"}


@app.get("/members", response_model=list[MemberRow])
def members(
    term: str,
    pledge_class: Optional[str] = None,
    max_gpa: Optional[float] = None,
    submitted: Optional[bool] = None,
    sort: Literal["name", "gpa"] = "name",
    chair: User = Depends(require_chair),
    session: Session = Depends(get_session),
):
    query = select(User).where(User.role == "member")
    if pledge_class:
        query = query.where(User.pledge_class == pledge_class)
    users = session.exec(query).all()

    grades = session.exec(select(GradeSubmission).where(GradeSubmission.term == term)).all()
    grades_by_user = {g.user_id: g for g in grades}

    # one row per member, blank grades if they have not submitted
    rows = []
    for u in users:
        row = MemberRow(name=u.name, email=u.email, pledge_class=u.pledge_class, term=term)
        grade = grades_by_user.get(u.id)
        if grade:
            row.gpa = grade.gpa
            row.credit_hours = grade.credit_hours
            row.submitted_at = grade.submitted_at
        rows.append(row)

    if submitted is True:
        rows = [r for r in rows if r.gpa is not None]
    if submitted is False:
        rows = [r for r in rows if r.gpa is None]
    if max_gpa is not None:
        rows = [r for r in rows if r.gpa is not None and r.gpa <= max_gpa]

    if sort == "gpa":
        # lowest gpa first, missing ones at the bottom
        rows.sort(key=lambda r: (r.gpa is None, r.gpa or 0))
    else:
        rows.sort(key=lambda r: r.name.lower())

    return rows
