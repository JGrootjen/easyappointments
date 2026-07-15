#!/usr/bin/env python3
"""Email the Zoom link to customers of upcoming online appointments, about 15 minutes before the start.

Runs from cron every 5 minutes on the booking VPS (see run.sh).
Reads the Easy!Appointments database through the docker compose db service and reuses the SMTP settings from /opt/easyappointments/app.env, so mail credentials live in exactly one place.
The meeting link itself comes from JWG_ZOOM_URL in /opt/jwg-booking/local.env, which exists only on the VPS and is never committed to this repository.
Appointment start times are stored as Europe/Berlin wall time (the provider timezone); verified against a live booking on 2026-07-15.
State: /opt/jwg-booking/state/zoom-reminders.log holds one "id|start_datetime" line per sent reminder, so a reschedule triggers a fresh reminder and reruns never send twice.

Run: /usr/bin/python3 /opt/jwg-booking/zoom_reminder.py [--lead-minutes 15] [--dry-run]
"""

import argparse
import smtplib
import subprocess
import sys
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from zoneinfo import ZoneInfo

EA_DIR = Path("/opt/easyappointments")
LOCAL_ENV = Path("/opt/jwg-booking/local.env")  # holds JWG_ZOOM_URL; VPS-only, never in the repository
STATE_FILE = Path("/opt/jwg-booking/state/zoom-reminders.log")
BERLIN = ZoneInfo("Europe/Berlin")
LATE_GRACE_MINUTES = 10  # still send if a very late booking slipped past a cron tick
STATE_KEEP_DAYS = 14


def log(msg):
    print(f"[{datetime.now(BERLIN):%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def read_env(path):
    """Parse a KEY=VALUE env file into a dict (no quoting rules, matching docker compose env_file)."""
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key] = value
    return env


def query(sql):
    """Run SQL against the EA database via the compose db service; returns rows of tab-split fields."""
    result = subprocess.run(
        ["/usr/bin/docker", "compose", "exec", "-T", "-e", f"JWG_SQL={sql}", "db", "sh", "-c",
         'exec mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" -N -B -e "$JWG_SQL"'],
        cwd=EA_DIR, capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"mysql query failed: {result.stderr.strip().splitlines()[-1:]}")
    return [line.split("\t") for line in result.stdout.splitlines() if line.strip()]


def load_state():
    if not STATE_FILE.exists():
        return set()
    return {line.strip() for line in STATE_FILE.read_text(encoding="utf-8").splitlines() if line.strip()}


def prune_state(sent, now_berlin):
    """Drop state lines whose appointment start is older than STATE_KEEP_DAYS."""
    cutoff = (now_berlin - timedelta(days=STATE_KEEP_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    kept = {key for key in sent if key.split("|", 1)[1] >= cutoff}
    if kept != sent:
        STATE_FILE.write_text("\n".join(sorted(kept)) + ("\n" if kept else ""), encoding="utf-8")
    return kept


def send_mail(env, to_name, to_email, subject, body, dry_run):
    msg = EmailMessage()
    msg["From"] = formataddr((env["MAIL_FROM_NAME"], env["MAIL_FROM_ADDRESS"]))
    msg["To"] = formataddr((to_name, to_email))
    msg["Reply-To"] = env.get("MAIL_REPLY_TO_ADDRESS", env["MAIL_FROM_ADDRESS"])
    msg["Subject"] = subject
    msg.set_content(body)
    if dry_run:
        log(f"DRY-RUN would send to {to_email}: {subject}")
        return
    host, port = env["MAIL_SMTP_HOST"], int(env["MAIL_SMTP_PORT"])
    if env.get("MAIL_SMTP_CRYPTO", "ssl").lower() == "ssl":
        server = smtplib.SMTP_SSL(host, port, timeout=30)
    else:
        server = smtplib.SMTP(host, port, timeout=30)
        server.starttls()
    with server:
        server.login(env["MAIL_SMTP_USER"], env["MAIL_SMTP_PASS"])
        server.send_message(msg)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lead-minutes", type=int, default=15)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    env = read_env(EA_DIR / "app.env")
    zoom_url = read_env(LOCAL_ENV).get("JWG_ZOOM_URL", "") if LOCAL_ENV.exists() else ""
    if not zoom_url:
        raise RuntimeError(f"JWG_ZOOM_URL missing from {LOCAL_ENV}; no reminders sent")
    now = datetime.now(BERLIN).replace(tzinfo=None)  # compare as Berlin wall time, like the DB
    lo = (now - timedelta(minutes=LATE_GRACE_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
    hi = (now + timedelta(minutes=args.lead_minutes)).strftime("%Y-%m-%d %H:%M:%S")

    rows = query(
        "SELECT a.id, a.start_datetime, s.name, s.duration, c.first_name, c.last_name, c.email, c.timezone "
        "FROM ea_appointments a "
        "JOIN ea_services s ON s.id = a.id_services "
        "JOIN ea_service_categories g ON g.id = s.id_service_categories "
        "JOIN ea_users c ON c.id = a.id_users_customer "
        "WHERE a.is_unavailability = 0 AND g.name LIKE '%online%' "
        f"AND a.start_datetime > '{lo}' AND a.start_datetime <= '{hi}' "
        "ORDER BY a.start_datetime"
    )

    sent = prune_state(load_state(), datetime.now(BERLIN))
    for appt_id, start_str, service, duration, first, last, email, customer_tz in rows:
        key = f"{appt_id}|{start_str}"
        if key in sent:
            continue
        start = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=BERLIN)
        when = f"{start:%H:%M} (Europe/Berlin)"
        if customer_tz and customer_tz != "Europe/Berlin":
            try:
                local = start.astimezone(ZoneInfo(customer_tz))
                when += f", {local:%H:%M} in your time zone ({customer_tz})"
            except Exception:
                pass
        body = (
            f"Hi {first},\n\n"
            f"your {service.lower()} with Jesse Grootjen starts at {when}.\n\n"
            f"Join via Zoom: {zoom_url}\n\n"
            f"If you cannot make it, just reply to this email.\n\n"
            f"Best,\nJesse\n"
        )
        subject = f"Zoom link for your {service.lower()} at {start:%H:%M}"
        try:
            send_mail(env, f"{first} {last}", email, subject, body, args.dry_run)
        except Exception as exc:
            log(f"SEND FAILED appointment {appt_id} to {email}: {exc}")
            continue
        if not args.dry_run:
            with STATE_FILE.open("a", encoding="utf-8") as fh:
                fh.write(key + "\n")
        log(f"sent Zoom link for appointment {appt_id} ({service}, {start_str}) to {email}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log(f"ERROR {exc}")
        sys.exit(1)
