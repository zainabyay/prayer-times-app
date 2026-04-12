from flask import Flask, Response, render_template
import urllib.request
import json
from icalendar import Calendar, Event, Alarm
from datetime import datetime, timedelta
import pytz
from flask_caching import Cache

app = Flask(__name__)

cache = Cache(app, config={
    'CACHE_TYPE': 'SimpleCache',
    'CACHE_DEFAULT_TIMEOUT': 43200
})

def get_monthly_prayer_times(city, year, month):
    cache_key = f"{city}-{year}-{month}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    url = f"https://api.aladhan.com/v1/calendarByCity/{year}/{month}?city={city}&country=GB&method=15"
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            data = json.loads(response.read())
        timings_by_day = {}
        for day_data in data['data']:
            date_str = day_data['date']['gregorian']['date']
            timings_by_day[date_str] = day_data['timings']
        cache.set(cache_key, timings_by_day)
        return timings_by_day
    except Exception as e:
        print(f"Error: {e}")
        return {}

def make_alarm(minutes_before):
    alarm = Alarm()
    alarm.add('action', 'DISPLAY')
    alarm.add('description', f'Prayer time in {minutes_before} minutes')
    alarm.add('trigger', timedelta(minutes=-minutes_before))
    return alarm

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/calendar/<city>.ics')
def prayer_calendar(city):
    cal = Calendar()
    cal.add('prodid', '-//Prayer Times//EN')
    cal.add('version', '2.0')
    cal.add('X-WR-CALNAME', f'Prayer Times - {city}')
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

    months_needed = set()
    for i in range(60):
        date = today + timedelta(days=i)
        months_needed.add((date.year, date.month))

    all_timings = {}
    for year, month in months_needed:
        monthly = get_monthly_prayer_times(city, year, month)
        all_timings.update(monthly)

    for i in range(60):
        date = today + timedelta(days=i)
        date_key = date.strftime('%d-%m-%Y')

        timings = all_timings.get(date_key)
        if not timings:
            continue

        for prayer, duration in prayer_durations.items():
            time_str = timings[prayer].split(' ')[0]
            hour, minute = map(int, time_str.split(':'))

            start = tz.localize(date.replace(tzinfo=None).replace(hour=hour, minute=minute, second=0, microsecond=0))
            end = start + timedelta(minutes=duration)

            event = Event()
            event.add('summary', f'Prayer - {prayer}')
            event.add('dtstart', start)
            event.add('dtend', end)
            event.add('description', f'Time for {prayer} - {duration} mins')
            event.add('uid', f'{prayer}-{date.strftime("%Y%m%d")}@prayertimes')
            event.add_component(make_alarm(10))
            cal.add_component(event)

        sunrise_str = timings['Sunrise'].split(' ')[0]
        hour, minute = map(int, sunrise_str.split(':'))
        sunrise_start = tz.localize(date.replace(tzinfo=None).replace(hour=hour, minute=minute, second=0, microsecond=0))
        sunrise_end = sunrise_start + timedelta(minutes=5)

        sunrise_event = Event()
        sunrise_event.add('summary', 'Sunrise')
        sunrise_event.add('dtstart', sunrise_start)
        sunrise_event.add('dtend', sunrise_end)
        sunrise_event.add('description', 'Sunrise - end of Fajr time')
        sunrise_event.add('uid', f'Sunrise-{date.strftime("%Y%m%d")}@prayertimes')
        cal.add_component(sunrise_event)

    response = Response(cal.to_ical(), mimetype='text/calendar')
    response.headers['Content-Disposition'] = 'inline'
    return response

if __name__ == '__main__':
    app.run(debug=True)
    