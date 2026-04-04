Yes — the cache is working but only after the first load. The problem is every new city has to fetch 60 days of API calls for the first time, which is slow.
The proper fix is to fetch all 60 days in parallel rather than one at a time. Right now it's doing this:
Day 1 → wait → Day 2 → wait → Day 3 → wait...
We want it to do this:
Day 1, Day 2, Day 3, Day 4... all at the same time
This is called concurrent requests and it'll cut the load time from 15 seconds down to 2-3 seconds even for a new city.
Go to VS Code, Ctrl+A, delete everything in app.py and paste this:
pythonfrom flask import Flask, Response, render_template
import urllib.request
import json
from icalendar import Calendar, Event
from datetime import datetime, timedelta
import pytz
from flask_caching import Cache
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

cache = Cache(app, config={
    'CACHE_TYPE': 'SimpleCache',
    'CACHE_DEFAULT_TIMEOUT': 43200
})

def get_prayer_times_for_date(city, date):
    cache_key = f"{city}-{date.strftime('%Y-%m-%d')}"
    cached = cache.get(cache_key)
    if cached:
        return date, cached

    date_str = date.strftime('%d-%m-%Y')
    url = f"https://api.aladhan.com/v1/timingsByCity/{date_str}?city={city}&country=GB&method=1"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read())
        timings = data['data']['timings']
        cache.set(cache_key, timings)
        return date, timings
    except:
        return date, None

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

    dates = [today + timedelta(days=i) for i in range(60)]

    results = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(get_prayer_times_for_date, city, date): date for date in dates}
        for future in as_completed(futures):
            date, timings = future.result()
            if timings:
                results[date] = timings

    for date in sorted(results.keys()):
        timings = results[date]

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
    