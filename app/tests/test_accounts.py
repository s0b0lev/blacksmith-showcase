import re

import pytest
from fastapi.testclient import TestClient

from showcase.main import accounts, app, outbox

VALID = {
    "first_name": "Ada",
    "last_name": "Lovelace",
    "email": "ada@example.com",
    "password": "correct horse",
}


@pytest.fixture(autouse=True)
def clean_accounts():
    accounts.clear()
    outbox.clear()
    yield
    accounts.clear()
    outbox.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def register(client: TestClient, **overrides):
    return client.post("/api/register", json={**VALID, **overrides})


def token_from_outbox() -> str:
    match = re.search(r"/verify\?token=([\w-]+)", outbox.messages[-1].body)
    assert match
    return match.group(1)


def verify(client: TestClient) -> None:
    assert client.get(f"/verify?token={token_from_outbox()}").status_code == 200


def test_register_returns_unverified_without_secrets(client: TestClient) -> None:
    res = register(client)
    assert res.status_code == 201
    assert res.json() == {"email": "ada@example.com", "verified": False}


@pytest.mark.parametrize("field", list(VALID))
@pytest.mark.parametrize("bad", [None, "", "   "])
def test_missing_or_blank_field(client: TestClient, field: str, bad) -> None:
    payload = {**VALID, field: bad}
    if bad is None:
        del payload[field]
    assert client.post("/api/register", json=payload).status_code == 422


@pytest.mark.parametrize("email", ["nope", "a@", "@b.com", "a@b", "a b@c.com"])
def test_invalid_email(client: TestClient, email: str) -> None:
    assert register(client, email=email).status_code == 422


def test_short_password(client: TestClient) -> None:
    assert register(client, password="short12").status_code == 422


def test_duplicate_email_case_insensitive(client: TestClient) -> None:
    assert register(client).status_code == 201
    assert register(client, email="ADA@Example.com").status_code == 409


def test_password_is_hashed(client: TestClient) -> None:
    register(client)
    user = accounts.users["ada@example.com"]
    assert VALID["password"] not in repr(user)


def test_verification_email_in_outbox(client: TestClient) -> None:
    register(client)
    assert len(outbox.messages) == 1
    msg = outbox.messages[0]
    assert msg.to == "ada@example.com"
    assert "Verify" in msg.body
    assert re.search(r"/verify\?token=[\w-]+", msg.body)


def test_verify_marks_user_verified(client: TestClient) -> None:
    register(client)
    res = client.get(f"/verify?token={token_from_outbox()}")
    assert res.status_code == 200
    assert "verified" in res.text.lower()
    assert 'href="/"' in res.text
    assert accounts.users["ada@example.com"].verified


def test_verify_bad_or_reused_token(client: TestClient) -> None:
    register(client)
    token = token_from_outbox()
    assert client.get("/verify?token=bogus").status_code == 400
    assert not accounts.users["ada@example.com"].verified
    assert client.get(f"/verify?token={token}").status_code == 200
    assert client.get(f"/verify?token={token}").status_code == 400


def test_bad_token_page_escapes_input(client: TestClient) -> None:
    res = client.get("/verify", params={"token": "<script>x</script>"})
    assert res.status_code == 400
    assert "<script>x" not in res.text


def login(client: TestClient, **overrides):
    return client.post(
        "/api/login",
        json={"email": VALID["email"], "password": VALID["password"], **overrides},
    )


def test_login_unverified_forbidden(client: TestClient) -> None:
    register(client)
    assert login(client).status_code == 403


def test_login_and_me(client: TestClient) -> None:
    register(client)
    verify(client)
    res = login(client)
    assert res.status_code == 200
    token = res.json()["token"]
    me = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json() == {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.com",
    }


def test_login_wrong_credentials(client: TestClient) -> None:
    register(client)
    verify(client)
    assert login(client, password="wrong password").status_code == 401
    assert login(client, email="who@example.com").status_code == 401


def test_me_requires_valid_token(client: TestClient) -> None:
    assert client.get("/api/me").status_code == 401
    bad = {"Authorization": "Bearer nope"}
    assert client.get("/api/me", headers=bad).status_code == 401


def test_home_has_signup_form(client: TestClient) -> None:
    html = client.get("/").text
    assert "Sign up" in html
    for name in ("first_name", "last_name", "email", "password"):
        assert f'name="{name}"' in html


def test_form_signup_shows_check_email(client: TestClient) -> None:
    res = client.post("/register", data=VALID)
    assert res.status_code == 200
    assert "check your email" in res.text.lower()
    assert len(outbox.messages) == 1


def test_form_signup_error_is_escaped(client: TestClient) -> None:
    data = {**VALID, "first_name": "<i>Ada</i>", "password": "short"}
    res = client.post("/register", data=data)
    assert res.status_code == 422
    assert "at least 8" in res.text
    assert "<i>Ada</i>" not in res.text
    assert "&lt;i&gt;Ada&lt;/i&gt;" in res.text
