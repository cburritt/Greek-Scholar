from conftest import PASSWORD, add_course, count, register, submit, user_exists, weeks_oldest_first
from models import AuditLog, ClassGrade, Course, FlagMute, Note, Submission


def setup_low_member(client):
    # one member with a low grade on the current week, so flags show up
    user_id, auth = register(client, "Jordan Lee", "jordan@test.com", pledge_class="Fall 2024")
    math = add_course(client, auth, "MATH 221", 4)
    phys = add_course(client, auth, "PHYS 213", 4)
    weeks = weeks_oldest_first(client, auth)
    current = weeks[-1]["id"]
    assert submit(client, auth, current, {math: 65, phys: 60}).status_code == 200
    return user_id, auth, math, phys, weeks


def log_actions(client, chair, user_id):
    return [r["action"] for r in client.get(f"/members/{user_id}/log", headers=chair).json()]


def test_mute_flag(client, chair, term):
    uid, _, math, phys, weeks = setup_low_member(client)
    current = weeks[-1]["id"]
    url = f"/members/{uid}/weeks/{current}/mutes"

    # class flags need the class, others must not have one
    assert client.post(url, json={"kind": "class_below", "reason": "sick"}, headers=chair).status_code == 400
    assert client.post(url, json={"kind": "gpa_below", "course_id": math, "reason": "sick"}, headers=chair).status_code == 400
    assert client.post(url, json={"kind": "bogus", "reason": "sick"}, headers=chair).status_code == 400
    assert client.post(url, json={"kind": "late", "reason": "x"}, headers=chair).status_code == 400  # not showing
    assert client.post(url, json={"kind": "gpa_below", "reason": ""}, headers=chair).status_code == 422

    res = client.post(url, json={"kind": "class_below", "course_id": phys, "reason": "Sick for two weeks"}, headers=chair)
    assert res.status_code == 200, res.text
    mute_id = res.json()["id"]
    assert client.post(url, json={"kind": "class_below", "course_id": phys, "reason": "again"}, headers=chair).status_code == 400

    row = client.get(f"/members?week_id={current}", headers=chair).json()[0]
    flags = {f["label"]: f for f in row["flags"]}
    assert flags["PHYS 213 below 70%"]["muted"] is True
    assert flags["PHYS 213 below 70%"]["mute_reason"] == "Sick for two weeks"
    # muting one class doesn't mute the other
    assert flags["MATH 221 below 70%"]["muted"] is False

    # status is untouched and the filter only skips the muted one
    assert row["status"] == "on_time"
    assert len(client.get(f"/members?week_id={current}&flag=class_below", headers=chair).json()) == 1

    # mute every remaining flag and the member drops out of "any flag"
    client.post(url, json={"kind": "class_below", "course_id": math, "reason": "sick"}, headers=chair)
    client.post(url, json={"kind": "gpa_below", "reason": "sick"}, headers=chair)
    assert client.get(f"/members?week_id={current}&flag=any", headers=chair).json() == []

    assert client.delete(f"/mutes/{mute_id}", headers=chair).status_code == 200
    assert client.delete(f"/mutes/{mute_id}", headers=chair).status_code == 404
    assert len(client.get(f"/members?week_id={current}&flag=any", headers=chair).json()) == 1

    actions = log_actions(client, chair, uid)
    assert actions.count("mute_flag") == 3 and actions.count("unmute_flag") == 1


def test_missing_week_can_be_muted_but_stays_missing(client, chair, term):
    uid, _ = register(client, "Sam", "sam@test.com")
    week1 = weeks_oldest_first(client, chair)[0]["id"]
    res = client.post(f"/members/{uid}/weeks/{week1}/mutes", json={"kind": "missing", "reason": "talked to him"}, headers=chair)
    assert res.status_code == 200
    row = client.get(f"/members?week_id={week1}", headers=chair).json()[0]
    assert row["status"] == "missing"
    assert client.get(f"/members?week_id={week1}&status=missing", headers=chair).json() != []
    stats = client.get("/stats/weekly", headers=chair).json()
    assert stats[0]["missing"] == 1


def test_correct_grade(client, chair, term):
    uid, member, math, phys, weeks = setup_low_member(client)
    current = weeks[-1]["id"]
    url = f"/members/{uid}/weeks/{current}/grades/{math}"

    assert client.put(url, json={"percent": 85}, headers=chair).status_code == 422  # reason required
    assert client.put(url, json={"percent": 65, "reason": "same"}, headers=chair).status_code == 400
    assert client.put(f"/members/{uid}/weeks/{weeks[0]['id']}/grades/{math}", json={"percent": 85, "reason": "x"}, headers=chair).status_code == 400
    # members can't use the chair route on themselves
    assert client.put(url, json={"percent": 100, "reason": "x"}, headers=member).status_code == 403

    res = client.put(url, json={"percent": 85, "reason": "Typo, checked with him"}, headers=chair)
    assert res.status_code == 200, res.text

    # the member sees the new grade and the marker
    mine = client.get("/submissions/me", headers=member).json()["weeks"][-1]
    by_code = {c["code"]: c for c in mine["classes"]}
    assert by_code["MATH 221"]["percent"] == 85
    assert by_code["MATH 221"]["corrected"] is True
    assert by_code["PHYS 213"]["corrected"] is False

    log = client.get(f"/members/{uid}/log", headers=chair).json()[0]
    assert (log["action"], log["old_value"], log["new_value"], log["reason"]) == ("correct_grade", "65%", "85%", "Typo, checked with him")
    assert log["course_code"] == "MATH 221" and log["actor_name"] == "Chair"

    # resubmitting replaces the correction and is logged
    submit(client, member, current, {math: 70, phys: 60})
    mine = client.get("/submissions/me", headers=member).json()["weeks"][-1]
    assert {c["code"]: c["corrected"] for c in mine["classes"]} == {"MATH 221": False, "PHYS 213": False}
    log = client.get(f"/members/{uid}/log", headers=chair).json()
    assert log[0]["action"] == "resubmit_grade"
    assert (log[0]["old_value"], log[0]["new_value"], log[0]["actor_name"]) == ("85%", "70%", "Jordan Lee")
    # only grades that changed are logged
    assert [r["action"] for r in log].count("resubmit_grade") == 1


def test_notes(client, chair, term):
    uid, member, _, _, weeks = setup_low_member(client)
    week = weeks[-1]["id"]

    assert client.post(f"/members/{uid}/notes", json={"text": "  "}, headers=chair).status_code == 400
    assert client.post(f"/members/{uid}/notes", json={"text": "x", "week_id": 99999}, headers=chair).status_code == 404
    res = client.post(f"/members/{uid}/notes", json={"text": "Talked about MATH 221", "week_id": week}, headers=chair)
    assert res.status_code == 200
    note = res.json()
    assert note["week_number"] == 4 and note["author_name"] == "Chair"
    assert note["created_at"] == note["updated_at"]

    # members can never read or write notes
    assert client.get(f"/members/{uid}/notes", headers=member).status_code == 403
    assert client.post(f"/members/{uid}/notes", json={"text": "hi"}, headers=member).status_code == 403

    edited = client.put(f"/notes/{note['id']}", json={"text": "Talked about MATH and PHYS"}, headers=chair).json()
    assert edited["text"] == "Talked about MATH and PHYS" and edited["week_id"] is None
    assert edited["updated_at"] != edited["created_at"]

    assert client.delete(f"/notes/{note['id']}", headers=chair).status_code == 200
    assert client.get(f"/members/{uid}/notes", headers=chair).json() == []
    assert log_actions(client, chair, uid) == ["delete_note", "edit_note", "add_note"]


def test_edit_member(client, chair, term):
    uid, member = register(client, "Alex", "alex@test.com", pledge_class="Fall 2024")
    res = client.patch(f"/members/{uid}", json={"name": " Alex Carter ", "pledge_class": "Spring 2025"}, headers=chair)
    assert res.status_code == 200
    assert (res.json()["name"], res.json()["pledge_class"]) == ("Alex Carter", "Spring 2025")
    assert client.patch(f"/members/{uid}", json={"name": " "}, headers=chair).status_code == 400
    # email can't be changed through this route
    client.patch(f"/members/{uid}", json={"email": "evil@test.com"}, headers=chair)
    assert client.get("/me", headers=member).json()["email"] == "alex@test.com"
    # the chair account can't be managed
    assert client.patch("/members/1", json={"name": "x"}, headers=chair).status_code == 404

    log = client.get(f"/members/{uid}/log", headers=chair).json()
    assert {(r["detail"], r["old_value"], r["new_value"]) for r in log} == {
        ("name", "Alex", "Alex Carter"),
        ("pledge_class", "Fall 2024", "Spring 2025"),
    }


def test_deactivate_and_reactivate(client, chair, term):
    uid, member = register(client, "Alex", "alex@test.com", pledge_class="Fall 2024")
    register(client, "Sam", "sam@test.com", pledge_class="Spring 2025")

    assert client.post(f"/members/{uid}/deactivate", json={"reason": ""}, headers=chair).status_code == 422
    assert client.post(f"/members/{uid}/deactivate", json={"reason": "Graduated"}, headers=chair).status_code == 200
    assert client.post(f"/members/{uid}/deactivate", json={"reason": "again"}, headers=chair).status_code == 400

    # locked out right away, even with the token they already had
    assert client.get("/me", headers=member).status_code == 401
    res = client.post("/login", data={"username": "alex@test.com", "password": PASSWORD})
    assert res.status_code == 403
    # a wrong password doesn't reveal the account is deactivated
    assert client.post("/login", data={"username": "alex@test.com", "password": "wrong-pass"}).status_code == 401

    # hidden from the chair views unless asked for
    assert [r["name"] for r in client.get("/members", headers=chair).json()] == ["Sam"]
    assert client.get("/pledge-classes", headers=chair).json() == ["Spring 2025"]
    assert client.get("/stats/weekly", headers=chair).json()[0]["missing"] == 1
    rows = client.get("/members?include_inactive=true", headers=chair).json()
    assert {r["name"]: r["active"] for r in rows} == {"Alex": False, "Sam": True}
    # their page still works for the chair
    assert client.get(f"/members/{uid}/history", headers=chair).json()["user"]["active"] is False

    assert client.post(f"/members/{uid}/reactivate", json={"reason": "Came back"}, headers=chair).status_code == 200
    assert client.post("/login", data={"username": "alex@test.com", "password": PASSWORD}).status_code == 200
    assert log_actions(client, chair, uid) == ["reactivate", "deactivate"]


def test_permanent_delete(client, chair, term):
    uid, _, math, _, weeks = setup_low_member(client)
    keep_id, keep = register(client, "Sam", "sam@test.com")
    keep_course = add_course(client, keep, "CIS 501")
    submit(client, keep, weeks[-1]["id"], {keep_course: 90})

    client.post(f"/members/{uid}/notes", json={"text": "note"}, headers=chair)
    client.post(f"/members/{uid}/weeks/{weeks[-1]['id']}/mutes", json={"kind": "gpa_below", "reason": "x"}, headers=chair)
    client.put(f"/members/{uid}/weeks/{weeks[-1]['id']}/grades/{math}", json={"percent": 80, "reason": "x"}, headers=chair)

    # the typed name has to match exactly
    bad = client.request("DELETE", f"/members/{uid}", json={"confirm_name": "jordan", "reason": "left"}, headers=chair)
    assert bad.status_code == 400
    assert user_exists(uid)
    assert client.request("DELETE", "/members/1", json={"confirm_name": "Chair", "reason": "x"}, headers=chair).status_code == 404

    res = client.request("DELETE", f"/members/{uid}", json={"confirm_name": "Jordan Lee", "reason": "Asked to be removed"}, headers=chair)
    assert res.status_code == 200, res.text

    assert not user_exists(uid)
    assert count(Course, Course.user_id == uid) == 0
    assert count(Submission, Submission.user_id == uid) == 0
    assert count(Note, Note.user_id == uid) == 0
    assert count(FlagMute, FlagMute.user_id == uid) == 0
    assert count(AuditLog, AuditLog.target_user_id == uid) == 0
    # only the anonymous delete record is left
    assert count(AuditLog, AuditLog.action == "delete_member", AuditLog.target_user_id.is_(None)) == 1
    assert client.post("/login", data={"username": "jordan@test.com", "password": PASSWORD}).status_code == 401

    # nobody else lost anything
    assert user_exists(keep_id)
    assert count(ClassGrade) == 1
    assert [r["name"] for r in client.get("/members", headers=chair).json()] == ["Sam"]


def test_members_cannot_manage(client, chair, term):
    uid, member, math, _, weeks = setup_low_member(client)
    week = weeks[-1]["id"]
    attempts = [
        ("post", f"/members/{uid}/weeks/{week}/mutes", {"kind": "gpa_below", "reason": "x"}),
        ("put", f"/members/{uid}/weeks/{week}/grades/{math}", {"percent": 100, "reason": "x"}),
        ("patch", f"/members/{uid}", {"name": "x"}),
        ("post", f"/members/{uid}/deactivate", {"reason": "x"}),
        ("get", f"/members/{uid}/log", None),
        ("get", f"/members/{uid}/history", None),
    ]
    for method, path, body in attempts:
        res = client.request(method.upper(), path, json=body, headers=member)
        assert res.status_code == 403, (path, res.status_code)
    res = client.request("DELETE", f"/members/{uid}", json={"confirm_name": "Jordan Lee", "reason": "x"}, headers=member)
    assert res.status_code == 403
    assert user_exists(uid)
