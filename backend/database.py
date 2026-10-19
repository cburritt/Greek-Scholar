from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, select

# sqlite file sits next to this script
DB_PATH = Path(__file__).parent / "grades.db"

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


def create_db():
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
