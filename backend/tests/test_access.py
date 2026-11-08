"""A1, A2, A6, A7, T9 and H2: the passcode gate, the hosted app and the health check."""

import uuid

import pytest
from app.access import COOKIE_NAME
from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient

PASSCODE = "correct horse"
WEEK = 7 * 24 * 60 * 60


def login(client, passcode=PASSCODE):
    return client.post("/api/login", json={"passcode": passcode})


@pytest.fixture
def photos(tmp_path):
    folder = tmp_path / "photos"
    folder.mkdir()
    (folder / "boy.jpg").write_bytes(b"boy-jpeg")
    return folder


def test_without_a_passcode_the_app_is_open_for_local_development(make_client):
    client, _ = make_client()
    assert client.get("/api/session").json() == {"required": False, "authenticated": True}
    assert client.post("/api/cases").status_code == 201


def test_a1_the_api_and_photos_are_closed_until_the_passcode_is_entered(make_client, photos):
    client, _ = make_client(access_passcode=PASSCODE, photos_dir=photos)
    assert client.post("/api/cases").status_code == 401
    assert client.get(f"/api/cases/{uuid.uuid4()}").status_code == 401
    assert client.get("/api/photos/boy.jpg").status_code == 401
    assert client.get("/api/session").json() == {"required": True, "authenticated": False}


def test_h2_health_check_needs_no_passcode(make_client):
    client, _ = make_client(access_passcode=PASSCODE)
    assert client.get("/api/health").status_code == 200


def test_a1_the_correct_passcode_opens_everything(make_client, photos):
    client, _ = make_client(access_passcode=PASSCODE, photos_dir=photos)
    assert login(client).status_code == 200
    assert client.get("/api/session").json() == {"required": True, "authenticated": True}
    assert client.post("/api/cases").status_code == 201
    photo = client.get("/api/photos/boy.jpg")
    assert photo.status_code == 200
    assert photo.content == b"boy-jpeg"
    assert photo.headers["content-type"] == "image/jpeg"


def test_a1_a_missing_photo_is_not_found_and_other_names_are_rejected(make_client, photos):
    client, _ = make_client(access_passcode=PASSCODE, photos_dir=photos)
    login(client)
    assert client.get("/api/photos/girl.jpg").status_code == 404
    assert client.get("/api/photos/secret.jpg").status_code == 422


def test_a1_a_wrong_passcode_is_refused_and_sets_no_cookie(make_client):
    client, _ = make_client(access_passcode=PASSCODE)
    response = login(client, "wrong")
    assert response.status_code == 401
    assert "set-cookie" not in response.headers
    assert client.post("/api/cases").status_code == 401


def test_a1_the_passcode_comparison_ignores_case_and_length_tricks_not(make_client):
    client, _ = make_client(access_passcode=PASSCODE)
    for attempt in ("Correct Horse", PASSCODE + " ", PASSCODE[:-1], "x" * 200):
        assert login(client, attempt).status_code == 401


def test_a1_oversized_or_empty_passcodes_are_rejected_without_counting(make_client):
    client, _ = make_client(access_passcode=PASSCODE)
    assert login(client, "").status_code == 422
    assert login(client, "x" * 201).status_code == 422


def test_a1_a_forged_cookie_is_refused(make_client):
    client, _ = make_client(access_passcode=PASSCODE)
    login(client)
    token = client.cookies.get(COOKIE_NAME)
    expiry, signature = token.split(".")

    intruder = TestClient(client.app)  # the same app, but without the real cookie
    for forged in (
        f"{expiry}.{'0' * len(signature)}",
        f"{int(expiry) + 1000}.{signature}",
        signature,
        "garbage",
        "",
    ):
        response = intruder.get("/api/session", headers={"Cookie": f"{COOKIE_NAME}={forged}"})
        assert response.json()["authenticated"] is False, forged


def test_a1_a_cookie_from_another_server_is_refused(make_client):
    first, _ = make_client(access_passcode=PASSCODE, session_secret="secret-one")
    second, _ = make_client(access_passcode=PASSCODE, session_secret="secret-two")
    login(first)
    token = first.cookies.get(COOKIE_NAME)
    response = second.get("/api/session", headers={"Cookie": f"{COOKIE_NAME}={token}"})
    assert response.json()["authenticated"] is False


def test_a1_the_cookie_lasts_a_week(make_client, clock):
    client, _ = make_client(access_passcode=PASSCODE)
    login(client)
    clock.advance(WEEK - 60)
    assert client.get("/api/session").json()["authenticated"] is True
    clock.advance(120)
    assert client.get("/api/session").json()["authenticated"] is False
    assert client.post("/api/cases").status_code == 401


def test_a2_ten_failures_lock_everyone_out_until_the_window_passes(make_client, clock):
    client, _ = make_client(access_passcode=PASSCODE)
    for _ in range(10):
        assert login(client, "nope").status_code == 401
    assert login(client, "nope").status_code == 429
    assert login(client).status_code == 429  # the right passcode too, while locked

    clock.advance(15 * 60 + 1)
    assert login(client).status_code == 200


def test_a2_successful_logins_do_not_count_as_failures(make_client):
    client, _ = make_client(access_passcode=PASSCODE)
    for _ in range(25):
        assert login(client).status_code == 200


def test_a2_a_lockout_does_not_log_out_people_who_are_already_in(make_client):
    client, _ = make_client(access_passcode=PASSCODE)
    login(client)
    attacker = TestClient(client.app)  # the same app, but without the real cookie
    for _ in range(11):
        login(attacker, "nope")
    assert client.post("/api/cases").status_code == 201


def test_a7_cookie_flags_in_production(make_client):
    client, _ = make_client(
        access_passcode=PASSCODE, production=True, base_url="https://testserver"
    )
    cookie = login(client).headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=lax" in cookie
    assert f"max-age={WEEK}" in cookie


def test_a7_cookie_is_not_secure_in_local_development(make_client):
    client, _ = make_client(access_passcode=PASSCODE)
    cookie = login(client).headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "secure" not in cookie


@pytest.mark.parametrize("passcode", [None, "", "short"])
def test_a6_production_refuses_to_start_without_a_strong_passcode(passcode):
    with pytest.raises(RuntimeError, match="ACCESS_PASSCODE"):
        create_app(Settings(production=True, access_passcode=passcode))


def test_a6_production_starts_with_a_passcode():
    create_app(Settings(production=True, access_passcode="long enough"))


def test_api_documentation_is_hidden_in_production(make_client):
    client, _ = make_client(access_passcode=PASSCODE, production=True)
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_t9_the_built_frontend_is_served_and_the_api_stays_closed(make_client, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>the app</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    client, _ = make_client(access_passcode=PASSCODE, frontend_dist=dist)

    assert client.get("/").text == "<html>the app</html>"
    assert client.get("/assets/app.js").status_code == 200
    assert client.post("/api/cases").status_code == 401
    assert client.get("/api/health").status_code == 200


def test_t9_without_a_build_there_is_no_page(make_client):
    client, _ = make_client()
    assert client.get("/").status_code == 404


def test_a8_the_real_photos_ship_with_the_app():
    folder = Settings().photos_dir
    assert (folder / "boy.jpg").is_file()
    assert (folder / "girl.jpg").is_file()
