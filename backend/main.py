from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select

import chair_routes
import member_routes
from auth import create_token, get_current_user, hash_password, verify_password
from database import create_db, get_session
from grading import load_scale
from models import GradeScale, HouseSettings, RegisterIn, Submission, Term, TokenOut, User, UserOut, WeekOut
from tracking import current_term, started_weeks, week_status


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

app.include_router(member_routes.router)
app.include_router(chair_routes.router)


def token_for(user: User) -> TokenOut:
    return TokenOut(access_token=create_token(user.id), user=UserOut.model_validate(user))


# auth

@app.post("/register", response_model=TokenOut, tags=["auth"])
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


@app.post("/login", response_model=TokenOut, tags=["auth"])
def login(form: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)):
    # the form calls it username but it is the email
    email = form.username.strip().lower()
    user = session.exec(select(User).where(User.email == email)).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Wrong email or password")
    return token_for(user)


@app.get("/me", response_model=UserOut, tags=["auth"])
def me(user: User = Depends(get_current_user)):
    return user


# shared

@app.get("/terms/current", response_model=Optional[Term], tags=["shared"])
def get_current_term(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return current_term(session)


@app.get("/weeks", response_model=list[WeekOut], tags=["shared"])
def get_weeks(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    # weeks of the current term that have started, newest first
    term = current_term(session)
    if term is None:
        return []
    weeks = started_weeks(session, term)

    subs = {}
    if user.role == "member":
        rows = session.exec(
            select(Submission).where(Submission.user_id == user.id, Submission.week_id.in_([w.id for w in weeks]))
        ).all()
        subs = {s.week_id: s for s in rows}

    now = datetime.now()
    out = []
    for w in reversed(weeks):
        item = WeekOut(id=w.id, number=w.number, start_date=w.start_date, due_at=w.due_at)
        if user.role == "member":
            item.status = week_status(w, subs.get(w.id), user, now)
        out.append(item)
    return out


@app.get("/settings/grade-scale", response_model=list[GradeScale], tags=["shared"])
def get_grade_scale(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return load_scale(session)


@app.get("/settings/house", response_model=HouseSettings, tags=["shared"])
def get_house_settings(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return session.exec(select(HouseSettings)).first()
