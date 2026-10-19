from typing import Optional

from sqlmodel import Session, select

from models import GradeScale

# typical scale, chair can change it in settings
DEFAULT_SCALE = [
    ("A", 90, 4.0),
    ("B", 80, 3.0),
    ("C", 70, 2.0),
    ("D", 60, 1.0),
    ("F", 0, 0.0),
]


def load_scale(session: Session) -> list[GradeScale]:
    # highest first so the first match wins
    return list(session.exec(select(GradeScale).order_by(GradeScale.min_percent.desc())).all())


def letter_and_points(percent: Optional[float], letter: Optional[str], scale: list[GradeScale]):
    # letter grades look up points directly, percents go through the cutoffs
    if letter:
        for row in scale:
            if row.letter == letter:
                return row.letter, row.points
        return letter, None

    if percent is None:
        return None, None

    for row in scale:
        if percent >= row.min_percent:
            return row.letter, row.points
    return None, None


def calc_gpa(entries: list[tuple[int, Optional[float]]]) -> Optional[float]:
    # entries are (credits, points), weighted by credits
    total_points = 0.0
    total_credits = 0
    for credits, points in entries:
        if points is None or credits <= 0:
            continue
        total_points += points * credits
        total_credits += credits

    if total_credits == 0:
        return None
    return round(total_points / total_credits, 2)
