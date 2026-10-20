import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

# point the app at a throwaway database and key before it is imported
TEST_DIR = tempfile.mkdtemp(prefix="greek-scholar-tests-")
os.environ["GS_DB_PATH"] = str(Path(TEST_DIR) / "test.db")
os.environ["SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-hs256"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, SQLModel, select  # noqa: E402

from auth import hash_password  # noqa: E402
from database import create_db, engine  # noqa: E402
from main import app  # noqa: E402
from models import User  # noqa: E402

PASSWORD = "password123"


@pytest.fixture
def client():
    # fresh database for every test
    SQLModel.metadata.drop_all(engine)
    create_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def chair(client):
    with Session(engine) as s:
        s.add(User(name="Chair", email="chair@test.com", password_hash=hash_password(PASSWORD), role="chair"))
        s.commit()
    return login(client, "chair@test.com")


@pytest.fixture
def term(client, chair):
    # started three weeks ago, due the day before each new week starts
    start = date.today() - timedelta(days=21)
    res = client.post(
        "/terms",
        json={
            "name": "Test Term",
            "start_date": start.isoformat(),
            "end_date": (date.today() + timedelta(days=60)).isoformat(),
            "due_weekday": (start.weekday() + 6) % 7,
            "due_time": "23:59",
        },
        headers=chair,
    )
    assert res.status_code == 200, res.text
    return res.json()


def headers(token):
    return {"Authorization": "Bearer " + token}


def login(client, email, password=PASSWORD):
    res = client.post("/login", data={"username": email, "password": password})
    assert res.status_code == 200, res.text
    return headers(res.json()["access_token"])


def register(client, name, email, pledge_class="Fall 2025", backdate=True):
    res = client.post("/register", json={"name": name, "email": email, "password": PASSWORD, "pledge_class": pledge_class})
    assert res.status_code == 200, res.text
    body = res.json()
    if backdate:
        # pretend they joined before the term so old weeks count
        with Session(engine) as s:
            user = s.get(User, body["user"]["id"])
            user.created_at = datetime.now() - timedelta(days=60)
            s.add(user)
            s.commit()
    return body["user"]["id"], headers(body["access_token"])


def weeks_oldest_first(client, auth):
    res = client.get("/weeks", headers=auth)
    assert res.status_code == 200, res.text
    return list(reversed(res.json()))


def add_course(client, auth, code, credits=3):
    res = client.post("/courses", json={"code": code, "credits": credits}, headers=auth)
    assert res.status_code == 200, res.text
    return res.json()["id"]


def submit(client, auth, week_id, grades):
    return client.post(
        "/submissions",
        json={"week_id": week_id, "grades": [{"course_id": c, "percent": p} for c, p in grades.items()]},
        headers=auth,
    )


def user_exists(user_id):
    with Session(engine) as s:
        return s.get(User, user_id) is not None


def count(model, *where):
    with Session(engine) as s:
        return len(s.exec(select(model).where(*where)).all())
