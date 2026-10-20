import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session

from database import get_session
from models import User

KEY_FILE = Path(__file__).parent / ".secret_key"


def load_secret_key() -> str:
    # use SECRET_KEY from the environment, otherwise make a random one once and keep it in a file
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    if KEY_FILE.exists():
        return KEY_FILE.read_text().strip()
    key = secrets.token_urlsafe(48)
    KEY_FILE.write_text(key)
    return key


SECRET_KEY = load_secret_key()
ALGORITHM = "HS256"
TOKEN_HOURS = 24

# tokenUrl makes the authorize button in /docs work
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# checked against when the email is unknown so login takes the same time either way
DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt()).decode()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    data = password.encode()
    # bcrypt rejects anything over 72 bytes, so that can never match
    if len(data) > 72:
        return False
    return bcrypt.checkpw(data, password_hash.encode())


def create_token(user_id: int) -> str:
    expires = datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)
    return jwt.encode({"sub": str(user_id), "exp": expires}, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), session: Session = Depends(get_session)) -> User:
    bad_token = HTTPException(status_code=401, detail="Invalid or expired token")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise bad_token from None

    user = session.get(User, user_id)
    # deactivated members lose access right away, even with a token
    if user is None or not user.active:
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
