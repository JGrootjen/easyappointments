#!/usr/bin/env python3
"""Regenerate the private ICS feed of booked appointments, for calendar subscription from Gmail or Outlook.

Runs from cron every 5 minutes on the booking VPS (see run.sh).
Reads the Easy!Appointments database through the docker compose db service and writes the feed atomically to /var/www/bookfeeds/<name>.ics, where <name> comes from the secret tokenised URL stored in /root/.jwg_ics_url (served by Caddy under book.jwgrootjen.com/feed/).
Appointment times are stored as Europe/Berlin wall time (the provider timezone); events are emitted with TZID=Europe/Berlin plus a VTIMEZONE definition so Google and Outlook render them correctly year-round.
Deleted or cancelled appointments vanish from the feed, and subscribed calendars drop them on their next refresh.

Run: /usr/bin/python3 /opt/jwg-booking/ics_feed.py
"""

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

EA_DIR = Path("/opt/easyappointments")
URL_FILE = Path("/root/.jwg_ics_url")
FEED_DIR = Path("/var/www/bookfeeds")
BERLIN = ZoneInfo("Europe/Berlin")
PAST_DAYS = 90  # keep recent history visible in the subscribed calendar

VTIMEZONE = (
    "BEGIN:VTIMEZONE\r\n"
    "TZID:Europe/Berlin\r\n"
    "BEGIN:DAYLIGHT\r\n"
    "TZOFFSETFROM:+0100\r\n"
    "TZOFFSETTO:+0200\r\n"
    "TZNAME:CEST\r\n"
    "DTSTART:19700329T020000\r\n"
    "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU\r\n"
    "END:DAYLIGHT\r\n"
    "BEGIN:STANDARD\r\n"
    "TZOFFSETFROM:+0200\r\n"
    "TZOFFSETTO:+0100\r\n"
    "TZNAME:CET\r\n"
    "DTSTART:19701025T030000\r\n"
    "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU\r\n"
    "END:STANDARD\r\n"
    "END:VTIMEZONE\r\n"
)


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


def esc(text):
    """Escape a value per RFC 5545 (backslash, semicolon, comma; the SQL already flattened newlines)."""
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")


def fold(line):
    """Fold a content line at 74 characters, continuation lines prefixed with one space (RFC 5545 3.1)."""
    out = []
    while len(line.encode("utf-8")) > 74:
        cut = 74
        while len(line[:cut].encode("utf-8")) > 74:
            cut -= 1
        out.append(line[:cut])
        line = " " + line[cut:]
    out.append(line)
    return "\r\n".join(out)


def compact(dt_str):
    """'YYYY-MM-DD HH:MM:SS' -> 'YYYYMMDDTHHMMSS'."""
    return dt_str.replace("-", "").replace(" ", "T").replace(":", "")


def main():
    feed_path = FEED_DIR / Path(URL_FILE.read_text(encoding="utf-8").strip()).name
    since = (datetime.now(BERLIN).replace(tzinfo=None) - timedelta(days=PAST_DAYS)).strftime("%Y-%m-%d %H:%M:%S")

    # CHAR(9/10/13) replacements flatten tabs and newlines in free-text fields so the TSV transport stays line-safe.
    flat = "REPLACE(REPLACE(REPLACE(COALESCE({0},''),CHAR(9),' '),CHAR(13),''),CHAR(10),' / ')"
    rows = query(
        "SELECT a.id, a.start_datetime, a.end_datetime, COALESCE(a.update_datetime,a.create_datetime), "
        f"s.name, {flat.format('s.location')}, g.name, "
        f"c.first_name, c.last_name, c.email, {flat.format('a.notes')} "
        "FROM ea_appointments a "
        "JOIN ea_services s ON s.id = a.id_services "
        "JOIN ea_service_categories g ON g.id = s.id_service_categories "
        "JOIN ea_users c ON c.id = a.id_users_customer "
        f"WHERE a.is_unavailability = 0 AND a.start_datetime >= '{since}' "
        "ORDER BY a.start_datetime"
    )

    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//jwgrootjen.com//booking feed//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        fold("X-WR-CALNAME:Bookings (jwgrootjen.com)"),
        "X-WR-TIMEZONE:Europe/Berlin",
        "REFRESH-INTERVAL;VALUE=DURATION:PT30M",
        "X-PUBLISHED-TTL:PT30M",
    ]
    body = "\r\n".join(lines) + "\r\n" + VTIMEZONE

    for appt_id, start, end, updated, service, location, category, first, last, email, notes in rows:
        updated_utc = (
            datetime.strptime(updated, "%Y-%m-%d %H:%M:%S")
            .replace(tzinfo=BERLIN).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        )
        desc = f"Booked via book.jwgrootjen.com ({category})\\nCustomer: {esc(first)} {esc(last)} <{email}>"
        if notes:
            desc += f"\\nNotes: {esc(notes)}"
        event = [
            "BEGIN:VEVENT",
            f"UID:ea-{appt_id}@book.jwgrootjen.com",
            f"DTSTAMP:{dtstamp}",
            f"LAST-MODIFIED:{updated_utc}",
            f"DTSTART;TZID=Europe/Berlin:{compact(start)}",
            f"DTEND;TZID=Europe/Berlin:{compact(end)}",
            fold(f"SUMMARY:{esc(service)}: {esc(first)} {esc(last)}"),
            fold(f"LOCATION:{esc(location)}"),
            fold(f"DESCRIPTION:{desc}"),
            "STATUS:CONFIRMED",
            "END:VEVENT",
        ]
        body += "\r\n".join(event) + "\r\n"

    body += "END:VCALENDAR\r\n"

    FEED_DIR.mkdir(parents=True, exist_ok=True)
    tmp = feed_path.with_suffix(".tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(feed_path)
    print(f"[{datetime.now(BERLIN):%Y-%m-%d %H:%M:%S}] wrote {feed_path} ({len(rows)} events)", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR {exc}", flush=True)
        sys.exit(1)
