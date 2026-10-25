import pytest
from fastapi.testclient import TestClient

from showcase.main import app, store


@pytest.fixture(autouse=True)
def clean_store():
    store.clear()
    yield
    store.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


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
    assert f'<h1>Notes</h1>\n  <p id="count">{label}</p>\n  <form' in html
    if n == 1:
        assert "1 notes" not in html
