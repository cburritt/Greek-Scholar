import os
from pathlib import Path

from sqlalchemy import event, inspect
from sqlmodel import Session, SQLModel, create_engine, select

# sqlite file sits next to this script, tests point GS_DB_PATH somewhere else
DB_PATH = Path(os.environ.get("GS_DB_PATH", Path(__file__).parent / "grades.db"))

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def turn_on_foreign_keys(connection, record):
    # sqlite ignores foreign keys unless asked
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def check_schema():
    # create_all adds new tables but not new columns, so catch an old database early
    existing = inspect(engine)
    for table in SQLModel.metadata.sorted_tables:
        if not existing.has_table(table.name):
            continue
        have = {c["name"] for c in existing.get_columns(table.name)}
        missing = [c.name for c in table.columns if c.name not in have]
        if missing:
            raise RuntimeError(
                f"grades.db is from an older version (table {table.name} is missing {', '.join(missing)}). "
                "Delete backend/grades.db and run python seed.py again."
            )


def create_db():
    check_schema()
    SQLModel.metadata.create_all(engine)
    ensure_defaults()


def ensure_defaults():
    # imported here so models and helpers can import this file
    from grading import DEFAULT_SCALE
    from models import FlagRule, GradeScale, HouseSettings
    from tracking import DEFAULT_FLAG_RULES

    with Session(engine) as session:
        if session.exec(select(HouseSettings)).first() is None:
            session.add(HouseSettings(grade_entry="percent"))

        if session.exec(select(GradeScale)).first() is None:
            for letter, min_percent, points in DEFAULT_SCALE:
                session.add(GradeScale(letter=letter, min_percent=min_percent, points=points))

        # add any flag kinds that are missing, keep the chair's edits on the rest
        existing = {r.kind for r in session.exec(select(FlagRule)).all()}
        for kind, threshold, enabled in DEFAULT_FLAG_RULES:
            if kind not in existing:
                session.add(FlagRule(kind=kind, threshold=threshold, enabled=enabled))

        session.commit()


def get_session():
    with Session(engine) as session:
        yield session
