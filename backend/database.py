from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

# sqlite file sits next to this script
DB_PATH = Path(__file__).parent / "grades.db"

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


def create_db():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
