# creates the chair account
# usage: python seed.py [email] [password]

import sys

from sqlmodel import Session, select

from auth import hash_password
from database import create_db, engine
from models import User

email = "chair@test.com"
password = "chair123"
if len(sys.argv) > 1:
    email = sys.argv[1].strip().lower()
if len(sys.argv) > 2:
    password = sys.argv[2]

create_db()

with Session(engine) as session:
    existing = session.exec(select(User).where(User.email == email)).first()
    if existing:
        existing.role = "chair"
        session.add(existing)
        session.commit()
        print(f"{email} already exists, made sure it is the chair")
    else:
        chair = User(name="Chair", email=email, password_hash=hash_password(password), role="chair")
        session.add(chair)
        session.commit()
        print(f"created chair account {email}")
