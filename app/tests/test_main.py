import pytest
from fastapi.testclient import TestClient

from showcase.main import app, store, users

V1 = "/api/v1"


@pytest.fixture(autouse=True)
def clean_store():
    store.clear()
    users.clear()
    yield
    store.clear()
    users.clear()


@pytest.fixture
def anon() -> TestClient:
    return TestClient(app)


@pytest.fixture
def client() -> TestClient:
    c = TestClient(app)
    res = c.post(f"{V1}/auth/register", json={"username": "alice", "password": "password1"})
    assert res.status_code == 201
    return c


def creds(username: str, password: str) -> dict[str, str]:
    return {"username": username, "password": password}


def test_docs_and_openapi(anon: TestClient) -> None:
    res = anon.get(f"{V1}/docs")
    assert res.status_code == 200 and "swagger-ui" in res.text.lower()
    paths = anon.get(f"{V1}/openapi.json").json()["paths"]
    for p in (
        "/health",
        "/auth/register",
        "/auth/login",
        "/auth/me",
        "/auth/logout",
        "/notes",
    ):
        assert V1 + p in paths


def test_v1_root_redirects_to_docs(anon: TestClient) -> None:
    res = anon.get(f"{V1}/", follow_redirects=False)
    assert res.status_code == 307 and res.headers["location"] == f"{V1}/docs"


def test_health(anon: TestClient) -> None:
    assert anon.get(f"{V1}/health").json() == {"status": "ok"}
    assert anon.get("/api/health").json() == {"status": "ok"}


def test_register_logs_in(anon: TestClient) -> None:
    res = anon.post(f"{V1}/auth/register", json=creds("bob", "password1"))
    assert res.status_code == 201 and res.json() == {"username": "bob"}
    assert "httponly" in res.headers["set-cookie"].lower()
    assert anon.get(f"{V1}/auth/me").json() == {"username": "bob"}


@pytest.mark.parametrize(
    ("username", "password", "status"),
    [
        ("ALICE", "password1", 409),
        ("   ", "password1", 400),
        ("ab", "password1", 400),
        ("carol", "short", 400),
        ("carol", "", 400),
    ],
)
def test_register_rejected(client: TestClient, username: str, password: str, status: int) -> None:
    other = TestClient(app)
    res = other.post(f"{V1}/auth/register", json=creds(username, password))
    assert res.status_code == status
    assert isinstance(res.json()["detail"], str)
    assert "session" not in res.cookies
    assert len(users.users) == 1


def test_login_success(client: TestClient) -> None:
    other = TestClient(app)
    res = other.post(f"{V1}/auth/login", json=creds("alice", "password1"))
    assert res.status_code == 200 and res.json() == {"username": "alice"}
    assert "session" in res.cookies


@pytest.mark.parametrize(
    ("username", "password"), [("alice", "wrongpass1"), ("nobody", "password1")]
)
def test_login_failure(client: TestClient, username: str, password: str) -> None:
    other = TestClient(app)
    res = other.post(f"{V1}/auth/login", json=creds(username, password))
    assert res.status_code == 401
    assert res.json() == {"detail": "Invalid username or password."}
    assert "session" not in res.cookies


def test_me(client: TestClient, anon: TestClient) -> None:
    assert client.get(f"{V1}/auth/me").json() == {"username": "alice"}
    assert anon.get(f"{V1}/auth/me").status_code == 401


def test_logout(client: TestClient) -> None:
    token = client.cookies["session"]
    res = client.post(f"{V1}/auth/logout")
    assert res.status_code == 204
    assert "session" not in client.cookies
    client.cookies.set("session", token)
    assert client.get(f"{V1}/auth/me").status_code == 401


def test_notes_start_empty(client: TestClient) -> None:
    assert client.get(f"{V1}/notes").json() == {"notes": [], "count": 0}


def test_create_note(client: TestClient) -> None:
    res = client.post(f"{V1}/notes", json={"text": "  hi  "})
    assert res.status_code == 201 and res.json() == {"text": "hi"}
    assert client.get(f"{V1}/notes").json() == {"notes": ["hi"], "count": 1}


@pytest.mark.parametrize("body", [{"text": "   "}, {}])
def test_empty_note_rejected(client: TestClient, body: dict[str, str]) -> None:
    assert client.post(f"{V1}/notes", json=body).status_code == 422


def test_notes_require_login(anon: TestClient) -> None:
    assert anon.get(f"{V1}/notes").status_code == 401
    assert anon.post(f"{V1}/notes", json={"text": "x"}).status_code == 401
    assert store.notes == []


def test_password_not_stored_plain(client: TestClient) -> None:
    _, salt, digest = users.users["alice"]
    assert b"password1" not in digest + salt


def test_old_notes_api_removed(client: TestClient) -> None:
    assert client.get("/api/notes").status_code == 404


@pytest.mark.parametrize("path", ["/login", "/register", "/profile", "/logout", "/notes"])
def test_old_html_routes_gone(client: TestClient, path: str) -> None:
    assert client.get(path, follow_redirects=False).status_code in (404, 405)
    assert client.post(path, data={"text": "x"}, follow_redirects=False).status_code == 404


def test_spa_shell(client: TestClient, anon: TestClient) -> None:
    for c in (anon, client):
        res = c.get("/")
        assert res.status_code == 200 and res.headers["content-type"].startswith("text/html")
        assert 'id="app"' in res.text and "vue" in res.text
        assert "v-html" not in res.text
        assert "alice" not in res.text
    assert "bootstrap@5.3.3/dist/css/bootstrap.min.css" in anon.get("/").text
