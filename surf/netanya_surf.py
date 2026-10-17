#!/usr/bin/env python3
"""
Netanya Surf Check - is today a good day to surf?

Fetches wave + wind forecasts for Netanya from the free Open-Meteo APIs
(no API key needed) and shows a simple web page with a verdict for a
beginner riding a 9' longboard.

Usage:
    python3 netanya_surf.py            # opens http://localhost:8000
    python3 netanya_surf.py --port 9000 --no-browser

Only the Python standard library is used.
"""

import argparse
import html
import json
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

# Just offshore of Netanya's beaches (the marine model needs a sea point).
LAT, LON = 32.33, 34.83
TZ = "Asia/Jerusalem"
DAYS = 4

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

# Daylight surfing hours we care about.
FIRST_HOUR, LAST_HOUR = 6, 18


# --------------------------------------------------------------------------
# Data fetching
# --------------------------------------------------------------------------

def _get_json(url, params):
    full = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full, headers={"User-Agent": "netanya-surf-check"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def fetch_forecast():
    """Return a list of hourly dicts with wave and wind data."""
    marine = _get_json(MARINE_URL, {
        "latitude": LAT, "longitude": LON, "timezone": TZ, "forecast_days": DAYS,
        "hourly": "wave_height,wave_period,wave_direction,"
                  "swell_wave_height,swell_wave_period,sea_surface_temperature",
    })["hourly"]
    weather = _get_json(WEATHER_URL, {
        "latitude": LAT, "longitude": 34.86, "timezone": TZ, "forecast_days": DAYS,
        "hourly": "wind_speed_10m,wind_direction_10m,wind_gusts_10m,temperature_2m",
    })["hourly"]

    wind_by_time = {t: i for i, t in enumerate(weather["time"])}
    hours = []
    for i, t in enumerate(marine["time"]):
        j = wind_by_time.get(t)
        if j is None or marine["wave_height"][i] is None:
            continue
        hours.append({
            "time": datetime.fromisoformat(t),
            "wave": marine["wave_height"][i],
            "period": marine["wave_period"][i] or 0,
            "wave_dir": marine["wave_direction"][i],
            "swell": marine["swell_wave_height"][i],
            "swell_period": marine["swell_wave_period"][i],
            "water_temp": marine["sea_surface_temperature"][i],
            "wind": weather["wind_speed_10m"][j] or 0,
            "wind_dir": weather["wind_direction_10m"][j] or 0,
            "gusts": weather["wind_gusts_10m"][j] or 0,
            "air_temp": weather["temperature_2m"][j],
        })
    return hours


# --------------------------------------------------------------------------
# Scoring for a beginner on a 9' longboard
# --------------------------------------------------------------------------

def wave_score(h):
    """A longboard catches small waves easily; beginners struggle above ~1.2 m."""
    if h < 0.25:
        return 0, "Flat - nothing to ride"
    if h < 0.4:
        return 55, "Small, but a 9' board can catch it"
    if h < 0.6:
        return 90, "Small and friendly - great for learning"
    if h <= 1.0:
        return 100, "Perfect beginner size"
    if h <= 1.3:
        return 60, "Getting big for a beginner"
    if h <= 1.8:
        return 20, "Too big - hard paddle-out, strong currents"
    return 0, "Dangerous for your level"


def period_score(p):
    """Longer period = cleaner, more organised waves."""
    if p < 4:
        return 30, "Very short period - choppy, messy"
    if p < 6:
        return 65, "Short period - a bit messy"
    if p < 9:
        return 100, "Good period - organised waves"
    return 90, "Long-period swell - can be powerful"


def wind_score(speed, direction):
    """Netanya's coast faces west, so wind FROM the east is offshore (good)."""
    offshore = 45 <= direction <= 135
    onshore = 225 <= direction <= 315
    if speed < 8:
        return 100, "Almost no wind - glassy"
    if speed < 15:
        if offshore:
            return 100, "Light offshore - clean faces"
        return (70, "Light onshore - slightly bumpy") if onshore else (85, "Light cross-shore")
    if speed < 25:
        if offshore:
            return 75, "Moderate offshore - OK but harder to paddle in"
        return (35, "Onshore - choppy and blown out") if onshore else (50, "Cross-shore - choppy")
    return 5, "Strong wind - not for beginners"


def score_hour(hour):
    ws, wnote = wave_score(hour["wave"])
    ps, pnote = period_score(hour["period"])
    ds, dnote = wind_score(hour["wind"], hour["wind_dir"])
    if ws == 0:
        total = 0
    else:
        total = 0.55 * ws + 0.15 * ps + 0.30 * ds
        # Gusty or the wave height alone makes it unsafe: cap it.
        if hour["gusts"] > 40:
            total = min(total, 30)
    hour["score"] = round(total)
    hour["notes"] = [wnote, pnote, dnote]
    return hour


def verdict(score):
    if score >= 75:
        return "GO SURF!", "go", "Conditions look great for you today."
    if score >= 50:
        return "Maybe", "maybe", "Surfable, but not ideal. Go if you're keen."
    return "Skip it", "skip", "Not a good day for your level."


def compass(deg):
    if deg is None:
        return "?"
    names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return names[int((deg % 360) / 45 + 0.5) % 8]


# --------------------------------------------------------------------------
# HTML UI
# --------------------------------------------------------------------------

def group_days(hours):
    # Skip hours that are already over, so "best time" is always still ahead.
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    days = {}
    for h in hours:
        if h["time"] >= now and FIRST_HOUR <= h["time"].hour <= LAST_HOUR:
            days.setdefault(h["time"].date(), []).append(h)
    return days


def render_page(hours):
    days = group_days(hours)
    if not days:
        return render_error("Forecast returned no data.")
    today_key = min(days)
    today = days[today_key]
    best = max(today, key=lambda h: h["score"])
    title, cls, blurb = verdict(best["score"])

    rows = []
    for h in today:
        _, hcls, _ = verdict(h["score"])
        rows.append(f"""
        <tr class="{'best' if h is best else ''}">
          <td>{h['time']:%H:%M}</td>
          <td>{h['wave']:.1f} m</td>
          <td>{h['period']:.0f} s</td>
          <td>{h['wind']:.0f} km/h {compass(h['wind_dir'])}</td>
          <td><div class="bar"><span class="{hcls}" style="width:{h['score']}%"></span></div>
              <small>{h['score']}</small></td>
        </tr>""")

    upcoming = []
    for d, hs in sorted(days.items()):
        if d == today_key:
            continue
        b = max(hs, key=lambda h: h["score"])
        t, c, _ = verdict(b["score"])
        upcoming.append(f"""
        <div class="day {c}">
          <b>{d:%a %d %b}</b>
          <span class="tag">{t}</span>
          <small>best ~{b['time']:%H:%M} &middot; {b['wave']:.1f} m &middot;
                 {b['wind']:.0f} km/h {compass(b['wind_dir'])}</small>
        </div>""")

    notes = "".join(f"<li>{html.escape(n)}</li>" for n in best["notes"])
    water = f"{best['water_temp']:.0f}&deg;C" if best["water_temp"] is not None else "?"
    air = f"{best['air_temp']:.0f}&deg;C" if best["air_temp"] is not None else "?"

    return PAGE.format(
        cls=cls, title=title, blurb=blurb, date=f"{today_key:%A, %d %B}",
        best_time=f"{best['time']:%H:%M}", score=best["score"],
        wave=f"{best['wave']:.1f}", period=f"{best['period']:.0f}",
        wind=f"{best['wind']:.0f}", wind_dir=compass(best["wind_dir"]),
        water=water, air=air, notes=notes, rows="".join(rows),
        upcoming="".join(upcoming), updated=f"{datetime.now():%H:%M}",
    )


def render_error(msg):
    return PAGE_ERROR.format(msg=html.escape(msg))


STYLE = """
<style>
  :root { --bg:#f4f8fb; --card:#fff; --ink:#1b2a36; --muted:#6b7c8a;
          --go:#1fa463; --maybe:#e7a417; --skip:#d64545; --line:#e3eaf0; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#0f1820; --card:#18242e; --ink:#e6eef4; --muted:#93a4b2; --line:#26343f; }
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font:16px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif; }
  main { max-width:760px; margin:0 auto; padding:24px 16px 48px; }
  h1 { font-size:20px; margin:0 0 4px; } .sub { color:var(--muted); margin:0 0 20px; }
  .card { background:var(--card); border-radius:16px; padding:20px; margin-bottom:16px;
          box-shadow:0 1px 3px rgba(0,0,0,.08); }
  .hero { border-left:8px solid var(--c); } .hero h2 { margin:0; font-size:40px; color:var(--c); }
  .go { --c:var(--go); } .maybe { --c:var(--maybe); } .skip { --c:var(--skip); }
  .stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:12px; margin-top:16px; }
  .stat { background:var(--bg); border-radius:10px; padding:10px 12px; }
  .stat b { display:block; font-size:22px; } .stat small { color:var(--muted); }
  ul { margin:12px 0 0; padding-left:20px; }
  table { width:100%; border-collapse:collapse; font-size:14px; }
  th, td { text-align:left; padding:7px 6px; border-bottom:1px solid var(--line); }
  th { color:var(--muted); font-weight:600; }
  tr.best td { font-weight:700; }
  .bar { display:inline-block; width:70px; height:8px; background:var(--line);
         border-radius:4px; overflow:hidden; vertical-align:middle; margin-right:6px; }
  .bar span { display:block; height:100%; background:var(--c); }
  .day { display:flex; flex-wrap:wrap; gap:4px 12px; align-items:baseline; padding:10px 0;
         border-bottom:1px solid var(--line); } .day:last-child { border:0; }
  .tag { color:var(--c); font-weight:700; } .day small { color:var(--muted); width:100%; }
  .foot { color:var(--muted); font-size:13px; }
  a.btn { display:inline-block; margin-top:8px; padding:8px 14px; border-radius:8px;
          background:var(--ink); color:var(--bg); text-decoration:none; }
  @media (max-width:520px) { th:nth-child(3), td:nth-child(3) { display:none; } }
</style>
"""

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Netanya Surf Check</title>""" + STYLE.replace("{", "{{").replace("}", "}}") + """</head>
<body><main>
  <h1>Netanya Surf Check</h1>
  <p class="sub">{date} &middot; for a beginner on a 9' longboard</p>

  <section class="card hero {cls}">
    <h2>{title}</h2>
    <p>{blurb} Best time: <b>{best_time}</b> (score {score}/100)</p>
    <div class="stats">
      <div class="stat"><b>{wave} m</b><small>wave height</small></div>
      <div class="stat"><b>{period} s</b><small>wave period</small></div>
      <div class="stat"><b>{wind} km/h {wind_dir}</b><small>wind</small></div>
      <div class="stat"><b>{water}</b><small>water / air {air}</small></div>
    </div>
    <ul>{notes}</ul>
  </section>

  <section class="card">
    <h3 style="margin-top:0">Today, hour by hour</h3>
    <table>
      <tr><th>Time</th><th>Waves</th><th>Period</th><th>Wind</th><th>Score</th></tr>
      {rows}
    </table>
  </section>

  <section class="card">
    <h3 style="margin-top:0">Next days</h3>
    {upcoming}
  </section>

  <p class="foot">
    Rule of thumb for you: 0.4&ndash;1.0 m waves, 6+ s period, light or easterly (offshore) wind.
    Always check the beach flags and lifeguards. Data: Open-Meteo. Updated {updated}.<br>
    <a class="btn" href="/">Refresh</a>
  </p>
</main></body></html>"""

PAGE_ERROR = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Netanya Surf Check</title>""" + STYLE.replace("{", "{{").replace("}", "}}") + """</head>
<body><main><section class="card hero skip"><h2>Couldn't load data</h2>
<p>{msg}</p><a class="btn" href="/">Try again</a></section></main></body></html>"""


# --------------------------------------------------------------------------
# Tiny local web server
# --------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/index.html"):
            self.send_error(404)
            return
        try:
            body = render_page([score_hour(h) for h in fetch_forecast()])
        except Exception as e:  # network errors, API changes, etc.
            body = render_error(f"{type(e).__name__}: {e}")
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def print_summary():
    """Quick text verdict in the terminal as well."""
    try:
        hours = [score_hour(h) for h in fetch_forecast()]
    except Exception as e:
        print(f"Could not fetch forecast: {e}")
        return
    today = group_days(hours)
    if not today:
        return
    day = today[min(today)]
    best = max(day, key=lambda h: h["score"])
    title, _, blurb = verdict(best["score"])
    print(f"\n  {title}  {blurb}")
    print(f"  Best at {best['time']:%H:%M}: {best['wave']:.1f} m waves, "
          f"{best['period']:.0f} s, wind {best['wind']:.0f} km/h {compass(best['wind_dir'])}\n")


def main():
    ap = argparse.ArgumentParser(description="Is it a good day to surf in Netanya?")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    print_summary()
    url = f"http://localhost:{args.port}/"
    server = HTTPServer(("127.0.0.1", args.port), Handler)
    print(f"  Surf report running at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBye - enjoy the waves!")


if __name__ == "__main__":
    main()
