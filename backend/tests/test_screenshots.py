import io

from conftest import (
    add_course,
    count,
    make_image,
    register,
    submit,
    upload_files,
    weeks_oldest_first,
)
from PIL import Image
from sqlmodel import Session, select

from database import engine
from models import ClassGrade, Screenshot, Submission


def setup_member(client, name="Alex", email="alex@test.com"):
    uid, auth = register(client, name, email)
    course = add_course(client, auth, "CIS 501")
    week = weeks_oldest_first(client, auth)[-1]["id"]
    return uid, auth, course, week


def my_week(client, auth):
    return client.get("/submissions/me", headers=auth).json()["weeks"][-1]


def test_screenshot_is_required(client, chair, term):
    _, auth, course, week = setup_member(client)
    res = submit(client, auth, week, {course: 90}, image=None)
    assert res.status_code == 422
    # nothing at all was saved
    assert count(Submission) == 0
    assert count(ClassGrade) == 0
    assert upload_files() == []


def test_submit_with_screenshot(client, chair, term):
    _, auth, course, week = setup_member(client)
    assert submit(client, auth, week, {course: 90}).status_code == 200
    mine = my_week(client, auth)
    assert mine["screenshot_id"] is not None
    assert len(upload_files()) == 1
    # the file is stored under a random name, not the uploaded one
    assert upload_files()[0] != "shot.png"
    assert upload_files()[0].endswith(".png")


def test_update_needs_a_new_screenshot_and_replaces_it(client, chair, term):
    _, auth, course, week = setup_member(client)
    submit(client, auth, week, {course: 90})
    first_file = upload_files()

    # no screenshot, no update, and the old grade stays
    assert submit(client, auth, week, {course: 70}, image=None).status_code == 422
    assert my_week(client, auth)["classes"][0]["percent"] == 90

    assert submit(client, auth, week, {course: 70}, image=make_image(color="red")).status_code == 200
    assert my_week(client, auth)["classes"][0]["percent"] == 70
    # one row, one file, and the old file is gone
    assert count(Screenshot) == 1
    assert len(upload_files()) == 1
    assert upload_files() != first_file


def test_bad_files_are_rejected(client, chair, term):
    _, auth, course, week = setup_member(client)
    fake = b"MZ\x90\x00 this is really a program" * 10
    assert submit(client, auth, week, {course: 90}, image=fake).status_code == 400
    assert submit(client, auth, week, {course: 90}, image=b"hello", filename="notes.txt", content_type="text/plain").status_code == 400
    assert submit(client, auth, week, {course: 90}, image=b"").status_code in (400, 422)
    gif = make_image(fmt="GIF")
    assert submit(client, auth, week, {course: 90}, image=gif, filename="a.gif", content_type="image/gif").status_code == 400
    too_big = b"\x89PNG" + b"0" * (5 * 1024 * 1024 + 10)
    res = submit(client, auth, week, {course: 90}, image=too_big)
    assert res.status_code == 400 and "too large" in res.json()["detail"]
    # none of those saved grades or files
    assert count(Submission) == 0
    assert upload_files() == []


def test_bad_grades_leave_no_file_behind(client, chair, term):
    _, auth, course, week = setup_member(client)
    other = add_course(client, auth, "MATH 221")
    # missing a class
    assert submit(client, auth, week, {course: 90}).status_code == 400
    # bad json
    res = client.post(
        "/submissions",
        data={"week_id": str(week), "grades": "not json"},
        files={"screenshot": ("s.png", make_image(), "image/png")},
        headers=auth,
    )
    assert res.status_code == 422
    assert submit(client, auth, week, {course: 90, other: 130}).status_code == 422
    assert upload_files() == []
    assert count(Submission) == 0


def test_exif_is_stripped_and_big_images_shrink(client, chair, term):
    _, auth, course, week = setup_member(client)
    exif = Image.Exif()
    exif[0x010F] = "Secret Phone Maker"  # camera make
    exif[0x8825] = {2: (40.0, 1.0, 0.0)}  # gps
    photo = make_image(fmt="JPEG", size=(3000, 1500), exif=exif.tobytes())
    assert submit(client, auth, week, {course: 90}, image=photo, filename="p.jpg", content_type="image/jpeg").status_code == 200

    shot_id = my_week(client, auth)["screenshot_id"]
    res = client.get(f"/screenshots/{shot_id}", headers=auth)
    assert res.status_code == 200
    saved = Image.open(io.BytesIO(res.content))
    assert saved.format == "JPEG"
    assert len(saved.getexif()) == 0
    assert max(saved.size) <= 2500


def test_who_can_see_a_screenshot(client, chair, term):
    _, alex, course, week = setup_member(client)
    _, sam = register(client, "Sam", "sam@test.com")
    submit(client, alex, week, {course: 90})
    shot_id = my_week(client, alex)["screenshot_id"]

    owner = client.get(f"/screenshots/{shot_id}", headers=alex)
    assert owner.status_code == 200
    assert owner.headers["content-type"] == "image/png"
    assert owner.headers["x-content-type-options"] == "nosniff"
    assert "no-store" in owner.headers["cache-control"]

    assert client.get(f"/screenshots/{shot_id}", headers=chair).status_code == 200
    # another member can't, and gets the same answer as a made up id
    assert client.get(f"/screenshots/{shot_id}", headers=sam).status_code == 404
    assert client.get("/screenshots/99999", headers=chair).status_code == 404
    assert client.get(f"/screenshots/{shot_id}").status_code == 401


def test_chair_sees_screenshot_ids(client, chair, term):
    uid, auth, course, week = setup_member(client)
    _, other = register(client, "Sam", "sam@test.com")
    submit(client, auth, week, {course: 90})
    rows = {r["name"]: r for r in client.get(f"/members?week_id={week}", headers=chair).json()}
    assert rows["Alex"]["screenshot_id"] is not None
    assert rows["Sam"]["screenshot_id"] is None
    history = client.get(f"/members/{uid}/history", headers=chair).json()["weeks"]
    assert history[-1]["screenshot_id"] == rows["Alex"]["screenshot_id"]
    assert history[0]["screenshot_id"] is None


def test_chair_correction_keeps_the_screenshot(client, chair, term):
    uid, auth, course, week = setup_member(client)
    submit(client, auth, week, {course: 60})
    before = my_week(client, auth)["screenshot_id"]
    res = client.put(f"/members/{uid}/weeks/{week}/grades/{course}", json={"percent": 65, "reason": "typo"}, headers=chair)
    assert res.status_code == 200
    assert my_week(client, auth)["screenshot_id"] == before
    assert len(upload_files()) == 1


def test_deleting_a_member_deletes_their_screenshots(client, chair, term):
    uid, auth, course, week = setup_member(client)
    _, sam, sam_course, _ = setup_member(client, "Sam", "sam@test.com")
    submit(client, auth, week, {course: 90})
    submit(client, sam, week, {sam_course: 80})
    assert len(upload_files()) == 2

    res = client.request("DELETE", f"/members/{uid}", json={"confirm_name": "Alex", "reason": "left"}, headers=chair)
    assert res.status_code == 200, res.text
    assert len(upload_files()) == 1
    with Session(engine) as s:
        assert len(s.exec(select(Screenshot)).all()) == 1


def test_huge_upload_refused_before_reading(client, chair, term):
    _, auth, course, week = setup_member(client)
    huge = b"\x89PNG" + b"0" * (7 * 1024 * 1024)
    res = submit(client, auth, week, {course: 90}, image=huge)
    assert res.status_code == 413
    assert upload_files() == []
