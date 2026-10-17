"""The web routes' safety rules: every change needs a signed-in admin and the page's CSRF token."""
import pytest

import app as rc_app
import config


@pytest.fixture
def client():
    rc_app.app.config["TESTING"] = True
    with rc_app.app.test_client() as c:
        yield c


def _sign_in(client):
    with client.session_transaction() as s:
        s["admin"] = True
        s["av"] = config.auth_version()
        s["csrf"] = "good-token"


def _post_routes():
    return sorted(r.rule for r in rc_app.app.url_map.iter_rules()
                  if "POST" in r.methods and r.rule.startswith("/admin"))


def test_there_are_admin_post_routes_to_check():
    assert len(_post_routes()) >= 15


@pytest.mark.parametrize("rule", _post_routes())
def test_every_change_is_refused_without_signing_in(client, rule):
    r = client.post(rule, json={})
    assert r.status_code == 401 and r.get_json()["ok"] is False   # the page's script then goes to /login


def test_signed_out_pages_go_to_login_and_feeds_say_401(client):
    for page in ("/admin", "/admin/settings", "/admin/backups"):
        r = client.get(page)
        assert r.status_code == 302 and "/login" in r.headers["Location"], page
    for feed in ("/api/admin.json", "/admin/config", "/admin/alerts", "/admin/games"):
        assert client.get(feed).status_code == 401, feed


@pytest.mark.parametrize("rule", _post_routes())
def test_every_change_is_refused_without_the_csrf_token(client, rule):
    _sign_in(client)
    for headers in ({}, {"X-CSRF-Token": "wrong"}):
        r = client.post(rule, json={}, headers=headers)
        assert r.status_code == 403, rule
        assert "reload it" in r.get_json()["error"]


def test_a_failed_action_comes_back_as_a_plain_400(client):
    _sign_in(client)
    r = client.post("/admin/servers/remove", json={"key": "no-such-server"},
                    headers={"X-CSRF-Token": "good-token"})
    assert r.status_code == 400 and r.get_json()["ok"] is False and r.get_json()["error"]


def test_the_alerts_step_is_ticked_once_a_destination_is_saved(client):
    _sign_in(client)
    config.update(lambda c: c.update(alert_destinations=[], alert_channel="none"))
    assert _alerts_item(client)["done"] is False
    config.update(lambda c: c.update(alert_destinations=[{"type": "ntfy", "url": "https://ntfy.sh/x"}]))
    assert _alerts_item(client)["done"] is True


def _alerts_item(client):
    items = client.get("/admin/checklist").get_json()["items"]
    return next(i for i in items if i["id"] == "alerts")


def test_pages_have_no_inline_styles():
    """The security policy allows styles only from style.css, so a style="" attribute in a page
    or in the page's code would be silently ignored by the browser."""
    import glob
    import os
    root = os.path.join(os.path.dirname(rc_app.__file__))
    files = glob.glob(os.path.join(root, "templates", "*.html")) + glob.glob(os.path.join(root, "static", "js", "*.js"))
    offenders = [os.path.basename(f) for f in files if "style=" in open(f, encoding="utf-8").read()]
    assert not offenders, f"inline style in: {offenders}"


def test_security_policy_allows_no_inline_styles(client):
    csp = client.get("/").headers["Content-Security-Policy"]
    assert "style-src 'self';" in csp + ";" and "unsafe-inline" not in csp
