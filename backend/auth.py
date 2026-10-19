import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session

from database import get_session
from models import User

# set SECRET_KEY in the environment for anything beyond local testing
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
ALGORITHM = "HS256"
TOKEN_HOURS = 24

# tokenUrl makes the authorize button in /docs work
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_token(user_id: int) -> str:
    expires = datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)
    return jwt.encode({"sub": str(user_id), "exp": expires}, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), session: Session = Depends(get_session)) -> User:
    bad_token = HTTPException(status_code=401, detail="Invalid or expired token")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise bad_token

    user = session.get(User, user_id)
    if user is None:
        raise bad_token
    return user


def require_chair(user: User = Depends(get_current_user)) -> User:
    if user.role != "chair":
        raise HTTPException(status_code=403, detail="Only the chair can do this")
    return user


def require_member(user: User = Depends(get_current_user)) -> User:
    if user.role != "member":
        raise HTTPException(status_code=403, detail="Only members can do this")
    return user
