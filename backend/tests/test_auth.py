from conftest import PASSWORD, headers, login, register


def test_register_and_login(client):
    user_id, auth = register(client, "Alex Carter", "Alex@Test.com", backdate=False)
    me = client.get("/me", headers=auth).json()
    # emails are stored lowercase
    assert me["email"] == "alex@test.com"
    assert me["role"] == "member"
    login(client, "ALEX@test.com")


def test_register_rules(client):
    base = {"name": "A", "email": "a@test.com", "password": PASSWORD, "pledge_class": "Fall 2025"}
    assert client.post("/register", json={**base, "password": "short"}).status_code == 422
    # bcrypt can only use 72 bytes
    assert client.post("/register", json={**base, "password": "x" * 73}).status_code == 422
    assert client.post("/register", json={**base, "email": "not-an-email"}).status_code == 422
    assert client.post("/register", json={**base, "name": "   "}).status_code == 400
    assert client.post("/register", json=base).status_code == 200
    dup = client.post("/register", json={**base, "email": "A@TEST.COM"})
    assert dup.status_code == 400


def test_register_can_never_make_a_chair(client):
    res = client.post(
        "/register",
        json={"name": "Sneaky", "email": "s@test.com", "password": PASSWORD, "pledge_class": "", "role": "chair"},
    )
    assert res.status_code == 200
    assert res.json()["user"]["role"] == "member"


def test_bad_logins_look_the_same(client):
    register(client, "Alex", "alex@test.com")
    wrong_password = client.post("/login", data={"username": "alex@test.com", "password": "nope-nope"})
    unknown_email = client.post("/login", data={"username": "nobody@test.com", "password": "nope-nope"})
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    # a huge password is a normal failure, not a crash
    too_long = client.post("/login", data={"username": "alex@test.com", "password": "x" * 500})
    assert too_long.status_code == 401


def test_tokens(client):
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers=headers("garbage")).status_code == 401
    # a token signed with another key is rejected
    import jwt

    forged = jwt.encode({"sub": "1"}, "some-other-key-that-is-long-enough-for-hs256", algorithm="HS256")
    assert client.get("/me", headers=headers(forged)).status_code == 401


def test_roles(client, chair, term):
    _, member = register(client, "Alex", "alex@test.com")
    chair_only = [
        ("get", "/members"),
        ("get", "/stats/weekly"),
        ("get", "/settings/flags"),
        ("get", "/pledge-classes"),
        ("get", "/members/1/log"),
        ("get", "/members/1/notes"),
        ("post", "/terms"),
        ("patch", "/members/2"),
    ]
    for method, path in chair_only:
        res = getattr(client, method)(path, headers=member)
        assert res.status_code in (403, 422), (path, res.status_code)
        if res.status_code == 422:
            # body checks can run first, but the route must still be chair only
            assert getattr(client, method)(path, headers=member, json={}).status_code in (403, 422)

    assert client.get("/members", headers=member).status_code == 403
    assert client.post("/courses", json={"code": "X 1", "credits": 3}, headers=chair).status_code == 403
    assert client.get("/submissions/me", headers=chair).status_code == 403
