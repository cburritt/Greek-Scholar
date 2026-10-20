from datetime import date, timedelta

from conftest import add_course, register, submit, weeks_oldest_first


def test_no_term_yet(client, chair):
    _, member = register(client, "Alex", "alex@test.com")
    assert client.get("/terms/current", headers=member).json() is None
    assert client.get("/weeks", headers=member).json() == []
    assert client.post("/courses", json={"code": "CIS 501", "credits": 3}, headers=member).status_code == 400


def test_weeks_and_statuses(client, chair, term):
    _, member = register(client, "Alex", "alex@test.com")
    weeks = weeks_oldest_first(client, member)
    assert [w["number"] for w in weeks] == [1, 2, 3, 4]
    # the first three are past due, the current one is open
    assert [w["status"] for w in weeks] == ["missing", "missing", "missing", "open"]
    # the chair gets weeks without a status
    assert all(w["status"] is None for w in client.get("/weeks", headers=chair).json())


def test_new_member_is_not_blamed_for_old_weeks(client, chair, term):
    _, member = register(client, "New", "new@test.com", backdate=False)
    statuses = [w["status"] for w in weeks_oldest_first(client, member)]
    assert statuses == ["not_member", "not_member", "not_member", "open"]


def test_courses(client, chair, term):
    _, member = register(client, "Alex", "alex@test.com")
    cid = add_course(client, member, "cis 501")
    courses = client.get("/courses", headers=member).json()
    assert courses[0]["code"] == "CIS 501"
    assert client.post("/courses", json={"code": "CIS 501", "credits": 3}, headers=member).status_code == 400
    assert client.post("/courses", json={"code": "X", "credits": 0}, headers=member).status_code == 422

    assert client.delete(f"/courses/{cid}", headers=member).status_code == 200
    assert client.get("/courses", headers=member).json() == []
    assert len(client.get("/courses?include_dropped=true", headers=member).json()) == 1
    # a dropped class can be added again
    add_course(client, member, "CIS 501")


def test_submit_rules_and_gpa(client, chair, term):
    _, member = register(client, "Alex", "alex@test.com")
    weeks = weeks_oldest_first(client, member)
    current = weeks[-1]["id"]

    assert submit(client, member, current, {1: 90}).status_code == 400  # no classes yet

    a = add_course(client, member, "CIS 501", 3)
    b = add_course(client, member, "MATH 221", 4)
    c = add_course(client, member, "ENGL 200", 3)

    assert submit(client, member, current, {a: 95}).status_code == 400  # missing classes
    assert submit(client, member, current, {a: 95, b: 85, c: 130}).status_code == 422
    assert submit(client, member, 99999, {a: 95, b: 85, c: 72}).status_code == 404

    res = submit(client, member, current, {a: 95, b: 85, c: 72})
    assert res.status_code == 200
    assert res.json()["late"] is False

    week = client.get("/submissions/me", headers=member).json()["weeks"][-1]
    # A*3 + B*4 + C*3 = 12 + 12 + 6 = 30 over 10 credits
    assert week["gpa"] == 3.0
    assert {x["code"]: x["letter"] for x in week["classes"]} == {"CIS 501": "A", "MATH 221": "B", "ENGL 200": "C"}
    assert week["flags"] == []  # members never see flags


def test_late_submission_counts_for_its_week(client, chair, term):
    _, member = register(client, "Alex", "alex@test.com")
    a = add_course(client, member, "CIS 501")
    first = weeks_oldest_first(client, member)[0]
    res = submit(client, member, first["id"], {a: 88})
    assert res.json()["late"] is True
    assert weeks_oldest_first(client, member)[0]["status"] == "late"


def test_future_week_rejected(client, chair):
    start = date.today() + timedelta(days=10)
    client.post(
        "/terms",
        json={"name": "Later", "start_date": start.isoformat(), "end_date": (start + timedelta(days=30)).isoformat(), "due_weekday": 6, "due_time": "23:59"},
        headers=chair,
    )
    _, member = register(client, "Alex", "alex@test.com")
    a = add_course(client, member, "CIS 501")
    # weeks that have not started are not listed and cannot be submitted
    assert client.get("/weeks", headers=member).json() == []
    from sqlmodel import Session, select

    from database import engine
    from models import Week

    with Session(engine) as s:
        week_id = s.exec(select(Week)).first().id
    assert submit(client, member, week_id, {a: 90}).status_code == 400


def test_members_cannot_use_each_others_data(client, chair, term):
    _, alex = register(client, "Alex", "alex@test.com")
    _, sam = register(client, "Sam", "sam@test.com")
    alex_course = add_course(client, alex, "CIS 501")
    sam_course = add_course(client, sam, "CIS 501")
    week = weeks_oldest_first(client, sam)[-1]["id"]

    assert submit(client, sam, week, {alex_course: 90}).status_code == 400
    assert client.delete(f"/courses/{alex_course}", headers=sam).status_code == 404
    assert submit(client, sam, week, {sam_course: 90}).status_code == 200
    # alex's history has nothing from sam
    assert all(w["classes"] == [] for w in client.get("/submissions/me", headers=alex).json()["weeks"])


def test_chair_table_filters_and_flags(client, chair, term):
    _, low = register(client, "Low", "low@test.com", pledge_class="Fall 2024")
    _, high = register(client, "High", "high@test.com", pledge_class="Spring 2025")
    lc = add_course(client, low, "CIS 501")
    hc = add_course(client, high, "CIS 501")
    weeks = weeks_oldest_first(client, low)
    w2, w3 = weeks[1]["id"], weeks[2]["id"]

    submit(client, low, w2, {lc: 85})
    submit(client, low, w3, {lc: 60})
    submit(client, high, w3, {hc: 95})

    rows = client.get(f"/members?week_id={w3}", headers=chair).json()
    by_name = {r["name"]: r for r in rows}
    labels = [f["label"] for f in by_name["Low"]["flags"]]
    assert "GPA below 2.5" in labels
    assert "CIS 501 below 70%" in labels
    assert "CIS 501 down 25%" in labels
    assert "GPA down 2" in labels
    assert "Late" in labels
    assert by_name["Low"]["gpa_change"] == -2.0

    assert [r["name"] for r in client.get(f"/members?week_id={w3}&flag=any", headers=chair).json()] == ["High", "Low"]
    assert [r["name"] for r in client.get(f"/members?week_id={w3}&flag=class_below", headers=chair).json()] == ["Low"]
    assert [r["name"] for r in client.get(f"/members?week_id={w3}&pledge_class=Spring%202025", headers=chair).json()] == ["High"]
    assert [r["name"] for r in client.get(f"/members?week_id={w3}&sort=gpa", headers=chair).json()] == ["Low", "High"]

    # week 1: both missing, and the streak flag needs 2
    w1_rows = client.get(f"/members?week_id={weeks[0]['id']}&status=missing", headers=chair).json()
    assert len(w1_rows) == 2
    streak = client.get(f"/members?week_id={w2}&flag=missed_in_row", headers=chair).json()
    assert [r["name"] for r in streak] == ["High"]

    # changing a rule changes the flags right away
    client.put("/settings/flags", json=[{"kind": "class_below", "threshold": 50, "enabled": True}], headers=chair)
    assert client.get(f"/members?week_id={w3}&flag=class_below", headers=chair).json() == []


def test_stats(client, chair, term):
    _, alex = register(client, "Alex", "alex@test.com")
    a = add_course(client, alex, "CIS 501")
    weeks = weeks_oldest_first(client, alex)
    submit(client, alex, weeks[2]["id"], {a: 85})
    stats = client.get("/stats/weekly", headers=chair).json()
    assert [s["missing"] for s in stats] == [1, 1, 0, 0]
    assert stats[2]["late"] == 1
    assert stats[2]["avg_gpa"] == 3.0


def test_settings_validation(client, chair):
    bad_scales = [
        [{"letter": "A", "min_percent": 90, "points": 4}],  # nothing at 0
        [{"letter": "A", "min_percent": 0, "points": 4}, {"letter": "A", "min_percent": 50, "points": 4}],  # same letter
        [{"letter": "F", "min_percent": 5, "points": 0}, {"letter": "A", "min_percent": 0, "points": 4}],  # backwards
        [],
    ]
    for scale in bad_scales:
        assert client.put("/settings/grade-scale", json=scale, headers=chair).status_code == 400

    plus_minus = [
        {"letter": "A", "min_percent": 93, "points": 4},
        {"letter": "A-", "min_percent": 90, "points": 3.7},
        {"letter": "B+", "min_percent": 87, "points": 3.3},
        {"letter": "F", "min_percent": 0, "points": 0},
    ]
    assert client.put("/settings/grade-scale", json=plus_minus, headers=chair).status_code == 200

    assert client.put("/settings/flags", json=[{"kind": "nope", "enabled": True}], headers=chair).status_code == 400
    assert client.put("/settings/flags", json=[{"kind": "gpa_below", "threshold": -1, "enabled": True}], headers=chair).status_code == 400
    assert client.put("/settings/flags", json=[{"kind": "gpa_below", "enabled": True}], headers=chair).status_code == 400


def test_future_term_does_not_replace_current(client, chair, term):
    start = date.today() + timedelta(days=90)
    client.post(
        "/terms",
        json={"name": "Next", "start_date": start.isoformat(), "end_date": (start + timedelta(days=100)).isoformat(), "due_weekday": 6, "due_time": "23:59"},
        headers=chair,
    )
    assert client.get("/terms/current", headers=chair).json()["name"] == "Test Term"
    bad = client.post(
        "/terms",
        json={"name": "Bad", "start_date": start.isoformat(), "end_date": start.isoformat(), "due_weekday": 6, "due_time": "23:59"},
        headers=chair,
    )
    assert bad.status_code == 400


def test_blank_and_repeat_course_actions(client, chair, term):
    _, member = register(client, "Alex", "alex@test.com")
    assert client.post("/courses", json={"code": "   ", "credits": 3}, headers=member).status_code == 400
    cid = add_course(client, member, "CIS 501")
    assert client.delete(f"/courses/{cid}", headers=member).status_code == 200
    assert client.delete(f"/courses/{cid}", headers=member).status_code == 400


def test_old_week_uses_the_classes_from_that_week(client, chair, term):
    _, member = register(client, "Alex", "alex@test.com")
    a = add_course(client, member, "CIS 501")
    b = add_course(client, member, "MATH 221")
    weeks = weeks_oldest_first(client, member)
    first = weeks[0]["id"]
    assert submit(client, member, first, {a: 80, b: 90}).status_code == 200

    # drop MATH now, then fix week 1, which still had MATH
    client.delete(f"/courses/{b}", headers=member)
    codes = [c["code"] for c in client.get(f"/weeks/{first}/courses", headers=member).json()]
    assert codes == ["CIS 501", "MATH 221"]
    assert submit(client, member, first, {a: 85, b: 90}).status_code == 200
    # the current week only has CIS
    current = weeks[-1]["id"]
    assert [c["code"] for c in client.get(f"/weeks/{current}/courses", headers=member).json()] == ["CIS 501"]
    assert submit(client, member, current, {a: 85, b: 90}).status_code == 400
    assert submit(client, member, current, {a: 85}).status_code == 200

    week1 = client.get("/submissions/me", headers=member).json()["weeks"][0]
    assert {c["code"]: c["percent"] for c in week1["classes"]} == {"CIS 501": 85, "MATH 221": 90}


def test_term_limits(client, chair):
    start = date.today()
    base = {"name": "T", "start_date": start.isoformat(), "due_weekday": 6, "due_time": "23:59"}
    too_long = client.post("/terms", json={**base, "end_date": (start + timedelta(days=400)).isoformat()}, headers=chair)
    assert too_long.status_code == 400
    blank = client.post("/terms", json={**base, "name": "  ", "end_date": (start + timedelta(days=30)).isoformat()}, headers=chair)
    assert blank.status_code == 400
    ok = client.post("/terms", json={**base, "end_date": (start + timedelta(days=30)).isoformat()}, headers=chair)
    assert ok.status_code == 200


def test_scale_blank_letter(client, chair):
    scale = [{"letter": " ", "min_percent": 90, "points": 4}, {"letter": "F", "min_percent": 0, "points": 0}]
    assert client.put("/settings/grade-scale", json=scale, headers=chair).status_code == 400
