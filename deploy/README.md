# Booking VPS automations

Host-side scripts for book.jwgrootjen.com (the Easy!Appointments instance in /opt/easyappointments). They live in /opt/jwg-booking on the VPS and are versioned here.

- `zoom_reminder.py`: emails the meeting link to the customer about 15 minutes before an online appointment. The link comes from JWG_ZOOM_URL in /opt/jwg-booking/local.env (VPS-only, never committed); SMTP settings come from /opt/easyappointments/app.env. Sent-state in /opt/jwg-booking/state/zoom-reminders.log.
- `ics_feed.py`: regenerates the private ICS feed of all appointments into /var/www/bookfeeds/, served by Caddy at the secret URL stored in /root/.jwg_ics_url. Subscribe from Google Calendar (Other calendars, From URL) or Outlook (Add calendar, Subscribe from web).
- `run.sh`: cron wrapper, `*/5 * * * * /opt/jwg-booking/run.sh`, with flock so runs never overlap.

Appointment `start_datetime` values are Europe/Berlin wall time (the provider timezone); verified against a live booking on 2026-07-15. Logs rotate nowhere; they are small (a line per send / per feed write with content changes only on activity).

Rotating the feed token: delete /root/.jwg_ics_url and the old .ics in /var/www/bookfeeds, write a new URL file (`https://book.jwgrootjen.com/feed/bookings-$(openssl rand -hex 24).ics`), wait for the next cron tick, and resubscribe the calendars.
