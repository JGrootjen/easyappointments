#!/usr/bin/env bash
# Cron wrapper for the booking automations: Zoom link reminders and the private ICS feed.
# Installed as: */5 * * * * /opt/jwg-booking/run.sh
set -u
exec 9>/opt/jwg-booking/.lock
flock -n 9 || exit 0
/usr/bin/python3 /opt/jwg-booking/zoom_reminder.py >> /opt/jwg-booking/logs/zoom_reminder.log 2>&1
/usr/bin/python3 /opt/jwg-booking/ics_feed.py >> /opt/jwg-booking/logs/ics_feed.log 2>&1
