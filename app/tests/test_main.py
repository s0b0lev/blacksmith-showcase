import pytest
from fastapi.testclient import TestClient

from showcase.main import app, store, users


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
    res = c.post("/register", data={"username": "alice", "password": "password1"})
    assert res.status_code == 200  # followed redirect to /
    return c


def test_health(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}


def test_notes_start_empty(client: TestClient) -> None:
    assert client.get("/api/notes").json() == {"notes": [], "count": 0}


def test_create_note_via_api(client: TestClient) -> None:
    res = client.post("/api/notes", json={"text": "  hello  "})
    assert res.status_code == 201
    assert res.json() == {"text": "hello"}
    assert client.get("/api/notes").json() == {"notes": ["hello"], "count": 1}


def test_empty_note_is_rejected(client: TestClient) -> None:
    res = client.post("/api/notes", json={"text": "   "})
    assert res.status_code == 422


def test_index_lists_notes_escaped(client: TestClient) -> None:
    client.post("/api/notes", json={"text": "<b>bold</b>"})
    html = client.get("/").text
    assert "&lt;b&gt;bold&lt;/b&gt;" in html
    assert "<b>bold</b>" not in html


def test_form_post_redirects_home(client: TestClient) -> None:
    res = client.post("/notes", data={"text": "from form"}, follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/"
    assert client.get("/api/notes").json() == {"notes": ["from form"], "count": 1}


def test_api_count_matches_notes(client: TestClient) -> None:
    for text in ("a", "b", "c"):
        client.post("/api/notes", json={"text": text})
    body = client.get("/api/notes").json()
    assert body["count"] == 3
    assert body["count"] == len(body["notes"])


@pytest.mark.parametrize(("n", "label"), [(0, "No notes yet"), (1, "1 note"), (3, "3 notes")])
def test_index_shows_count(client: TestClient, n: int, label: str) -> None:
    for i in range(n):
        client.post("/api/notes", json={"text": f"note {i}"})
    html = client.get("/").text
    assert f'<p id="count" class="text-muted">{label}</p>' in html
    if n == 1:
        assert "1 notes" not in html


def post(c: TestClient, path: str, **data: str):
    return c.post(path, data=data, follow_redirects=False)


def test_index_requires_login(anon: TestClient) -> None:
    res = anon.get("/", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/login"


@pytest.mark.parametrize(("path", "other"), [("/login", "/register"), ("/register", "/login")])
def test_auth_pages(anon: TestClient, path: str, other: str) -> None:
    res = anon.get(path)
    assert res.status_code == 200
    assert 'name="username"' in res.text and 'type="password"' in res.text
    assert 'class="form-control"' in res.text and 'type="submit"' in res.text
    assert f'href="{other}"' in res.text


def test_register_logs_in(anon: TestClient) -> None:
    res = post(anon, "/register", username="bob", password="password1")
    assert res.status_code == 303 and res.headers["location"] == "/"
    assert "session" in res.cookies
    assert anon.get("/").status_code == 200


@pytest.mark.parametrize(
    ("username", "password", "status"),
    [
        ("ALICE", "password1", 409),
        ("   ", "password1", 400),
        ("carol", "   ", 400),
        ("carol", "", 400),
    ],
)
def test_register_rejected(client: TestClient, username: str, password: str, status: int) -> None:
    other = TestClient(app)
    res = post(other, "/register", username=username, password=password)
    assert res.status_code == status
    assert "alert alert-danger" in res.text
    assert "session" not in res.cookies
    assert len(users.users) == 1


def test_login_success(client: TestClient) -> None:
    other = TestClient(app)
    res = post(other, "/login", username="alice", password="password1")
    assert res.status_code == 303 and res.headers["location"] == "/"
    assert "session" in res.cookies


@pytest.mark.parametrize(
    ("username", "password"), [("alice", "wrongpass1"), ("nobody", "password1")]
)
def test_login_failure(client: TestClient, username: str, password: str) -> None:
    other = TestClient(app)
    res = post(other, "/login", username=username, password=password)
    assert res.status_code == 401
    assert "alert alert-danger" in res.text
    assert "session" not in res.cookies


def test_password_not_stored_or_rendered(client: TestClient) -> None:
    _, salt, digest = users.users["alice"]
    assert digest != b"password1" and b"password1" not in digest + salt
    for path in ("/", "/profile", "/login", "/register"):
        assert "password1" not in client.get(path, follow_redirects=False).text


def test_index_has_bootstrap_notes_ui(client: TestClient) -> None:
    html = client.get("/").text
    assert "No notes yet" in html
    assert 'action="/notes"' in html and 'id="notes"' in html and "list-group" in html


def test_form_note_escaped(client: TestClient) -> None:
    res = post(client, "/notes", text="<b>x</b>")
    assert res.status_code == 303 and res.headers["location"] == "/"
    html = client.get("/").text
    assert "&lt;b&gt;x&lt;/b&gt;" in html and "<b>x</b>" not in html


def test_notes_post_requires_login(anon: TestClient) -> None:
    res = post(anon, "/notes", text="sneaky")
    assert res.status_code == 303 and res.headers["location"] == "/login"
    assert store.notes == []


def test_header_on_authenticated_pages(client: TestClient) -> None:
    for path in ("/", "/profile"):
        html = client.get(path).text
        assert '<nav class="navbar' in html
        assert "Blacksmith showcase</a>" in html
        assert 'dropdown-toggle"' in html and ">alice</button>" in html
        assert 'href="/profile"' in html and 'action="/logout"' in html


def test_profile(client: TestClient, anon: TestClient) -> None:
    res = client.get("/profile")
    assert res.status_code == 200 and "alice" in res.text
    res = anon.get("/profile", follow_redirects=False)
    assert res.status_code == 303 and res.headers["location"] == "/login"


def test_logout(client: TestClient) -> None:
    res = post(client, "/logout")
    assert res.status_code == 303 and res.headers["location"] == "/login"
    assert client.get("/", follow_redirects=False).headers["location"] == "/login"


@pytest.mark.parametrize("path", ["/login", "/register"])
def test_logged_in_redirected_from_auth_pages(client: TestClient, path: str) -> None:
    res = client.get(path, follow_redirects=False)
    assert res.status_code == 303 and res.headers["location"] == "/"


def test_username_escaped(anon: TestClient) -> None:
    post(anon, "/register", username="<script>", password="password1")
    for path in ("/", "/profile"):
        html = anon.get(path).text
        assert "&lt;script&gt;" in html and "<script>" not in html


def test_bootstrap_assets_pinned(client: TestClient, anon: TestClient) -> None:
    for c, path in ((client, "/"), (anon, "/login"), (anon, "/register")):
        html = c.get(path).text
        assert "bootstrap@5.3.3/dist/css/bootstrap.min.css" in html
        assert "bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js" in html


def test_api_needs_no_session(anon: TestClient) -> None:
    assert anon.get("/api/health").json() == {"status": "ok"}
    assert anon.post("/api/notes", json={"text": "x"}).status_code == 201
    assert anon.get("/api/notes").json() == {"notes": ["x"], "count": 1}
