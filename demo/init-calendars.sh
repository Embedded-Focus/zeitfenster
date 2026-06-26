#!/bin/sh
set -e

RADICALE_URL="${RADICALE_URL:-http://radicale:5232}"
RADICALE_USER="${RADICALE_USER:-reader}"
RADICALE_PASS="${RADICALE_PASS:-demopassword}"

echo "Waiting for Radicale..."
until curl -s -u "$RADICALE_USER:$RADICALE_PASS" "$RADICALE_URL" > /dev/null 2>&1; do
    sleep 1
done
echo "Radicale is up."

create_calendar() {
    local path="$1"
    local name="$2"
    curl -s -u "$RADICALE_USER:$RADICALE_PASS" \
        -X MKCALENDAR "$RADICALE_URL/$path" \
        -H "Content-Type: application/xml" \
        -d "<?xml version='1.0' encoding='UTF-8'?>
<C:mkcalendar xmlns:C='urn:ietf:params:xml:ns:caldav' xmlns:D='DAV:'>
  <D:set>
    <D:prop>
      <D:displayname>$name</D:displayname>
      <C:supported-calendar-component-set>
        <C:comp name='VEVENT'/>
      </C:supported-calendar-component-set>
    </D:prop>
  </D:set>
</C:mkcalendar>" 2>&1 || true
}

put_event() {
    local calendar_path="$1"
    local filename="$2"
    local ics_data="$3"
    curl -s -u "$RADICALE_USER:$RADICALE_PASS" \
        -X PUT "$RADICALE_URL/$calendar_path/$filename" \
        -H "Content-Type: text/calendar" \
        -d "$ics_data" 2>&1 || true
}

echo "Creating calendars..."
create_calendar "reader/work" "Work"
create_calendar "reader/personal" "Personal"

echo "Adding events..."

put_event "reader/work" "standup.ics" "BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Demo//EN
BEGIN:VEVENT
UID:demo-standup-recurring@zeitfenster
DTSTART;TZID=Europe/Vienna:20260101T093000
DTEND;TZID=Europe/Vienna:20260101T100000
SUMMARY:Daily Standup
RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR
END:VEVENT
END:VCALENDAR"

put_event "reader/work" "planning.ics" "BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Demo//EN
BEGIN:VEVENT
UID:demo-planning-weekly@zeitfenster
DTSTART;TZID=Europe/Vienna:20260105T140000
DTEND;TZID=Europe/Vienna:20260105T153000
SUMMARY:Sprint Planning
RRULE:FREQ=WEEKLY;BYDAY=MO
END:VEVENT
END:VCALENDAR"

put_event "reader/personal" "lunch.ics" "BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Demo//EN
BEGIN:VEVENT
UID:demo-lunch-recurring@zeitfenster
DTSTART;TZID=Europe/Vienna:20260101T120000
DTEND;TZID=Europe/Vienna:20260101T130000
SUMMARY:Lunch Break
RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR
END:VEVENT
END:VCALENDAR"

put_event "reader/personal" "gym.ics" "BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Demo//EN
BEGIN:VEVENT
UID:demo-gym-weekly@zeitfenster
DTSTART;TZID=Europe/Vienna:20260107T170000
DTEND;TZID=Europe/Vienna:20260107T183000
SUMMARY:Gym
RRULE:FREQ=WEEKLY;BYDAY=WE,FR
END:VEVENT
END:VCALENDAR"

echo "Demo calendars initialized."
