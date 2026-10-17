"""certs.py — a browser-trusted HTTPS certificate from Let's Encrypt.

GameDash ships with a self-signed certificate, which makes browsers show a
warning. This module replaces it with a free, trusted one — without needing
root:

  * certbot (installed in GameDash's own Python environment) proves control of
    the domain over HTTP on a high port; the operator's router forwards the
    internet's port 80 to that port;
  * the issued certificate is copied over the files gunicorn already serves
    (the self-signed pair is kept as a fallback) and the dashboard restarts;
  * a daily systemd user timer renews it and repeats the copy + restart.

Let's Encrypt's terms must be accepted by the operator (a checkbox on the
form) — never on their behalf.
"""
from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time

import config
import jobs
import paths
import systemd
from applog import app_log, audit_log
from games.base import ActionError

LE_DIR = paths.data("letsencrypt")
CERT = os.path.join(paths.CERTS_DIR, "cert.pem")
KEY = os.path.join(paths.CERTS_DIR, "key.pem")
UNITS = os.path.expanduser("~/.config/systemd/user")
TERMS_URL = "https://letsencrypt.org/repository/"
_DOMAIN_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[a-z0-9.-]{3,253}$", re.I)

cert_job = jobs.Job("certificate")


def status_job() -> dict:
    return cert_job.status()


def certbot_path() -> str | None:
    p = os.path.join(os.path.dirname(sys.executable), "certbot")
    return p if os.path.isfile(p) else shutil.which("certbot")


def _dirs() -> list[str]:
    return ["--config-dir", os.path.join(LE_DIR, "config"),
            "--work-dir", os.path.join(LE_DIR, "work"),
            "--logs-dir", os.path.join(LE_DIR, "logs")]


def info() -> dict:
    """What certificate is being served: who issued it, for which name, until when."""
    out = {"trusted": False, "issuer": "", "subject": "", "expires": "", "days_left": None}
    try:
        r = subprocess.run(["openssl", "x509", "-in", CERT, "-noout", "-issuer", "-subject",
                            "-enddate"], capture_output=True, text=True, timeout=10)
        for line in r.stdout.splitlines():
            k, _, v = line.partition("=")
            if k == "issuer":
                out["issuer"] = v.strip()
            elif k == "subject":
                out["subject"] = v.strip()
            elif k == "notAfter":
                out["expires"] = v.strip()
                try:
                    end = time.mktime(time.strptime(v.strip(), "%b %d %H:%M:%S %Y %Z"))
                    out["days_left"] = int((end - time.time()) / 86400)
                except ValueError:
                    pass
        # self-signed = it vouches for itself
        out["trusted"] = bool(out["issuer"]) and out["issuer"] != out["subject"]
    except Exception:
        pass
    cfg = config.load()
    out["domain"] = cfg.get("cert_domain", "")
    out["http_port"] = _http_port(cfg)
    out["auto_renew"] = os.path.isfile(os.path.join(UNITS, "gamedash-cert-renew.timer"))
    return out


def _port_free(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False


def install_issued(domain: str) -> None:
    """Copy the issued certificate over the pair gunicorn serves. The original
    self-signed pair is kept once as *.selfsigned.pem so it can be put back."""
    live = os.path.join(LE_DIR, "config", "live", domain)
    chain, key = os.path.join(live, "fullchain.pem"), os.path.join(live, "privkey.pem")
    if not (os.path.isfile(chain) and os.path.isfile(key)):
        raise ActionError("The certificate files weren't found after issuing.")
    for cur in (CERT, KEY):
        keep = cur.replace(".pem", ".selfsigned.pem")
        if os.path.isfile(cur) and not os.path.exists(keep):
            shutil.copy2(cur, keep)
    for src, dst in ((chain, CERT), (key, KEY)):
        tmp = dst + ".new"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f, open(src, "rb") as s:
            f.write(s.read())
        os.replace(tmp, dst)


def restart_dashboard() -> None:
    """Restart the web service so it serves the new certificate. Detached, so
    the request that triggered it can finish first."""
    subprocess.Popen(["systemctl", "--user", "restart", "--no-block", "gamedash.service"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _write_renew_units(http_port: int) -> None:
    py = sys.executable
    manage = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manage.py")
    svc = f"""[Unit]
Description=gamedash: renew the HTTPS certificate (Let's Encrypt)

[Service]
Type=oneshot
Environment=GAMEDASH_HOME={paths.HOME}
ExecStart={certbot_path()} renew --non-interactive --http-01-port {http_port} {' '.join(_dirs())} --deploy-hook "{py} {manage} install-cert"
"""
    timer = """[Unit]
Description=gamedash: check the HTTPS certificate twice a day

[Timer]
OnCalendar=*-*-* 04,16:30:00
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
"""
    os.makedirs(UNITS, exist_ok=True)
    for name, text in (("gamedash-cert-renew.service", svc), ("gamedash-cert-renew.timer", timer)):
        with open(os.path.join(UNITS, name), "w", encoding="utf-8") as f:
            f.write(text)
    systemd.run("daemon-reload", timeout=30)
    systemd.run("enable", "--now", "gamedash-cert-renew.timer", timeout=30)


def _explain(output: str) -> str:
    """Turn certbot's failure output into something a person can act on."""
    o = output.lower()
    if "timeout during connect" in o or "connection refused" in o or "firewall" in o:
        return ("Let's Encrypt couldn't reach this computer through your router. Check the "
                "port-forwarding rule (internet port 80 → this computer, the port shown above) "
                "and that your internet provider doesn't block port 80, then try again.")
    if "nxdomain" in o or "dns problem" in o or "no valid ip addresses" in o:
        return ("That name doesn't lead to this network yet. Check the spelling, and that the "
                "name points at your public address.")
    if "too many" in o or "rate limit" in o:
        return ("Let's Encrypt has temporarily stopped accepting requests for this name because "
                "of repeated attempts. Wait an hour (after several failures) and try again.")
    if "unauthorized" in o or "invalid response" in o:
        return ("Something else answered on port 80 for that name — the router rule may point at "
                "a different device or port.")
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    return "The certificate couldn't be issued: " + (lines[-1][:300] if lines else "unknown error")


def _http_port(cfg: dict | None = None) -> int:
    """The local port Let's Encrypt's check reaches (the router forwards internet port 80 here)."""
    return int((cfg or config.load()).get("cert_http_port") or config.DEFAULTS["cert_http_port"])


def start(domain: str, email: str, agree: bool, dashboard_port: int = 8443) -> dict:
    """Start getting a certificate in the background. dashboard_port is only used in the
    "reload the page at …" message once it's done."""
    domain = (domain or "").strip().lower().rstrip(".")
    email = (email or "").strip()
    if not _DOMAIN_RE.match(domain):
        raise ActionError("Enter the name people use to reach this dashboard, like "
                          "mygames.example.net (a name, not a number — Let's Encrypt can't "
                          "issue certificates for bare IP addresses here).")
    if email and not _EMAIL_RE.match(email):
        raise ActionError("That email address doesn't look right. Leave it blank to skip it.")
    if not agree:
        raise ActionError(f"Please read Let's Encrypt's terms ({TERMS_URL}) and tick the box to "
                          f"agree — they require it before issuing a certificate.")
    if not certbot_path():
        raise ActionError("The certificate tool (certbot) isn't installed. Run the GameDash "
                          "installer again, then retry.")
    http_port = _http_port()
    if not _port_free(http_port):
        raise ActionError(f"Port {http_port} on this computer is in use by another program, and "
                          f"the certificate check needs it for a moment.")
    cert_job.begin("A certificate request is already running.", domain=domain, step="Asking Let's Encrypt")
    audit_log.info("certificate REQUEST domain=%s", domain)
    threading.Thread(target=_run, args=(domain, email, http_port, dashboard_port), name="cert",
                     daemon=True).start()
    return {"ok": True, "message": "Requesting the certificate — this takes up to a minute."}


def _run(domain: str, email: str, http_port: int, dashboard_port: int) -> None:
    base = [certbot_path(), "certonly", "--standalone", "--preferred-challenges", "http",
            "--http-01-port", str(http_port), "-d", domain, "--non-interactive", "--agree-tos",
            *(["-m", email] if email else ["--register-unsafely-without-email"]), *_dirs()]
    try:
        os.makedirs(LE_DIR, mode=0o700, exist_ok=True)
        # Rehearse against Let's Encrypt's test service first: a mis-set router
        # then costs nothing, instead of using up the real service's attempts.
        for label, extra in (("Testing the connection from Let's Encrypt", ["--dry-run"]),
                             ("Issuing the certificate", [])):
            cert_job.step(label)
            r = subprocess.run(base + extra, capture_output=True, text=True, timeout=300)
            if r.returncode != 0:
                raise ActionError(_explain(r.stdout + "\n" + r.stderr))
        install_issued(domain)
        config.update(lambda c: c.update({"cert_domain": domain}))
        _write_renew_units(http_port)
        cert_job.finish(True, f"Done — a trusted certificate for {domain} is installed and will renew "
                              f"itself. The dashboard is restarting; reload this page in a few seconds "
                              f"using https://{domain}:{dashboard_port}/")
        audit_log.info("certificate ISSUED domain=%s", domain)
        time.sleep(2)   # let the page read the result before the restart
        restart_dashboard()
    except ActionError as e:
        cert_job.finish(False, str(e))
        audit_log.warning("certificate FAILED domain=%s", domain)
    except Exception as e:
        app_log.exception("certificate request crashed")
        cert_job.finish(False, f"Something went wrong requesting the certificate: {e}")
