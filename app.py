from flask import Flask, Response, render_template, request
import urllib.request
import json
from icalendar import Calendar, Event, Alarm
from datetime import datetime, timedelta, date
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

    url = f"https://api.aladhan.com/v1/calendarByCity/{year}/{month}?city={city}&method=15"
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

def get_timezone_for_city(city):
    city_lower = city.lower().strip()
    timezone_map = {
        'dubai': 'Asia/Dubai',
        'abu dhabi': 'Asia/Dubai',
        'riyadh': 'Asia/Riyadh',
        'jeddah': 'Asia/Riyadh',
        'mecca': 'Asia/Riyadh',
        'medina': 'Asia/Riyadh',
        'cairo': 'Africa/Cairo',
        'istanbul': 'Europe/Istanbul',
        'karachi': 'Asia/Karachi',
        'lahore': 'Asia/Karachi',
        'islamabad': 'Asia/Karachi',
        'dhaka': 'Asia/Dhaka',
        'kuala lumpur': 'Asia/Kuala_Lumpur',
        'jakarta': 'Asia/Jakarta',
        'tokyo': 'Asia/Tokyo',
        'new york': 'America/New_York',
        'toronto': 'America/Toronto',
        'los angeles': 'America/Los_Angeles',
        'paris': 'Europe/Paris',
        'amsterdam': 'Europe/Amsterdam',
        'berlin': 'Europe/Berlin',
    }
    return timezone_map.get(city_lower, 'Europe/London')

def make_alarm(minutes_before):
    alarm = Alarm()
    alarm.add('action', 'DISPLAY')
    alarm.add('description', f'Prayer time in {minutes_before} minutes')
    alarm.add('trigger', timedelta(minutes=-minutes_before))
    return alarm

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/faq')
def faq():
    return render_template('faq.html')

@app.route('/calendar/<city>.ics')
def prayer_calendar(city):
    reminders = request.args.get('reminders', 'true').lower() == 'true'
    holiday_city = request.args.get('holiday_city', '').strip()
    holiday_start_str = request.args.get('holiday_start', '')
    holiday_end_str = request.args.get('holiday_end', '')

    # Parse holiday dates if provided
    holiday_start = None
    holiday_end = None
    if holiday_city and holiday_start_str and holiday_end_str:
        try:
            holiday_start = datetime.strptime(holiday_start_str, '%Y-%m-%d').date()
            holiday_end = datetime.strptime(holiday_end_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    cal = Calendar()
    cal.add('prodid', '-//Prayer Times//EN')
    cal.add('version', '2.0')
    cal.add('X-WR-CALNAME', f'Prayer Times - {city}')
    cal.add('X-WR-TIMEZONE', 'Europe/London')
    cal.add('REFRESH-INTERVAL;VALUE=DURATION', 'PT30M')

    home_tz = pytz.timezone('Europe/London')
    today = datetime.now(home_tz)

    prayer_durations = {
        'Fajr': 20,
        'Dhuhr': 15,
        'Asr': 15,
        'Maghrib': 10,
        'Isha': 15
    }

    # Gather all months needed for home city
    months_home = set()
    months_holiday = set()

    for i in range(60):
        current_date = (today + timedelta(days=i)).date()
        if holiday_start and holiday_end and holiday_start <= current_date <= holiday_end:
            months_holiday.add((current_date.year, current_date.month))
        else:
            months_home.add((current_date.year, current_date.month))

    # Fetch timings for home city
    all_timings_home = {}
    for year, month in months_home:
        monthly = get_monthly_prayer_times(city, year, month)
        all_timings_home.update(monthly)

    # Fetch timings for holiday city
    all_timings_holiday = {}
    if holiday_city and months_holiday:
        for year, month in months_holiday:
            monthly = get_monthly_prayer_times(holiday_city, year, month)
            all_timings_holiday.update(monthly)

    for i in range(60):
        current_date = (today + timedelta(days=i)).date()
        date_key = (today + timedelta(days=i)).strftime('%d-%m-%Y')

        # Decide which city and timezone to use for this day
        is_holiday = (holiday_start and holiday_end and 
                      holiday_start <= current_date <= holiday_end and 
                      holiday_city)

        if is_holiday:
            timings = all_timings_holiday.get(date_key)
            tz = pytz.timezone(get_timezone_for_city(holiday_city))
        else:
            timings = all_timings_home.get(date_key)
            tz = home_tz

        if not timings:
            continue

        for prayer, duration in prayer_durations.items():
            time_str = timings[prayer].split(' ')[0]
            hour, minute = map(int, time_str.split(':'))

            dt = datetime.combine(current_date, datetime.min.time()).replace(hour=hour, minute=minute, second=0)
            start = tz.localize(dt)
            end = start + timedelta(minutes=duration)

            event = Event()
            event.add('summary', f'Prayer - {prayer}')
            event.add('dtstart', start)
            event.add('dtend', end)
            event.add('description', f'Time for {prayer} - {duration} mins')
            event.add('uid', f'{prayer}-{current_date.strftime("%Y%m%d")}@prayertimes')
            if reminders:
                event.add_component(make_alarm(10))
            cal.add_component(event)

        sunrise_str = timings['Sunrise'].split(' ')[0]
        hour, minute = map(int, sunrise_str.split(':'))
        sunrise_dt = datetime.combine(current_date, datetime.min.time()).replace(hour=hour, minute=minute, second=0)
        sunrise_start = tz.localize(sunrise_dt)
        sunrise_end = sunrise_start + timedelta(minutes=5)

        sunrise_event = Event()
        sunrise_event.add('summary', 'Sunrise')
        sunrise_event.add('dtstart', sunrise_start)
        sunrise_event.add('dtend', sunrise_end)
        sunrise_event.add('description', 'Sunrise - end of Fajr time')
        sunrise_event.add('uid', f'Sunrise-{current_date.strftime("%Y%m%d")}@prayertimes')
        cal.add_component(sunrise_event)

    response = Response(cal.to_ical(), mimetype='text/calendar')
    response.headers['Content-Disposition'] = 'inline'
    return response

if __name__ == '__main__':
    app.run(debug=True)
