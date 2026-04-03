from flask import Flask, Response, render_template
import urllib.request
import json
from icalendar import Calendar, Event
from datetime import datetime, timedelta
import pytz

app = Flask(__name__)

def get_prayer_times_for_date(city, date):
    date_str = date.strftime('%d-%m-%Y')
    url = f"https://api.aladhan.com/v1/timingsByCity/{date_str}?city={city}&country=GB&method=1"
    with urllib.request.urlopen(url) as response:
        data = json.loads(response.read())
    return data['data']['timings']

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/calendar/<city>.ics')
def prayer_calendar(city):
    cal = Calendar()
    cal.add('prodid', '-//Prayer Times//EN')
    cal.add('version', '2.0')
    cal.add('X-WR-CALNAME', f'🕌 Prayer Times - {city}')
    cal.add('X-WR-TIMEZONE', 'Europe/London')
    cal.add('REFRESH-INTERVAL;VALUE=DURATION', 'P1D')

    tz = pytz.timezone('Europe/London')
    today = datetime.now(tz)

    prayer_durations = {
        'Fajr': 20,
        'Dhuhr': 15,
        'Asr': 15,
        'Maghrib': 10,
        'Isha': 15
    }

    for i in range(60):
        date = today + timedelta(days=i)

        try:
            timings = get_prayer_times_for_date(city, date)
        except:
            continue

        for prayer, duration in prayer_durations.items():
            time_str = timings[prayer]
            hour, minute = map(int, time_str.split(':'))

            start = date.replace(hour=hour, minute=minute, second=0, microsecond=0)
            end = start + timedelta(minutes=duration)

            event = Event()
            event.add('summary', f'🕌 {prayer}')
            event.add('dtstart', start)
            event.add('dtend', end)
            event.add('description', f'Time for {prayer} — {duration} mins')
            event.add('uid', f'{prayer}-{date.strftime("%Y%m%d")}@prayertimes')
            cal.add_component(event)

        sunrise_str = timings['Sunrise']
        hour, minute = map(int, sunrise_str.split(':'))
        sunrise_start = date.replace(hour=hour, minute=minute, second=0, microsecond=0)
        sunrise_end = sunrise_start + timedelta(minutes=5)

        sunrise_event = Event()
        sunrise_event.add('summary', '🌅 Sunrise')
        sunrise_event.add('dtstart', sunrise_start)
        sunrise_event.add('dtend', sunrise_end)
        sunrise_event.add('description', 'Sunrise — end of Fajr time')
        sunrise_event.add('uid', f'Sunrise-{date.strftime("%Y%m%d")}@prayertimes')
        cal.add_component(sunrise_event)

    response = Response(cal.to_ical(), mimetype='text/calendar')
    response.headers['Content-Disposition'] = 'inline'
    return response

if __name__ == '__main__':
    app.run(debug=True)
