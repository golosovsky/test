# Bus 605 Tracker - Udim Station

Real-time arrival tracker for the 605 bus line at Udim station (southbound).

## Quick Start

```bash
node server.js
```

Then open http://localhost:3000 in your browser.

## How It Works

- Searches for bus stops by name or code (pre-filled with "Udim")
- Shows real-time 605 bus arrivals with estimated minutes
- Also shows other lines serving the same stop
- Auto-refreshes every 30 seconds

## Data Source

Uses the [busnearby.co.il](https://app.busnearby.co.il) API for real-time Israeli public transit data, sourced from the Ministry of Transport's SIRI-SM system.

## Requirements

- Node.js (no external dependencies)

## Usage

1. Run `node server.js`
2. The app auto-searches for Udim stops
3. Select the southbound stop from the list
4. Watch arrival times update in real-time

The stop code is printed on the physical bus stop sign. You can also search by name.

---

# Netanya Surf Check

A small Python script that tells you whether today is a good day to surf in Netanya,
tuned for a beginner on a 9' longboard.

```bash
python3 surf/netanya_surf.py
```

It prints a quick verdict in the terminal and opens http://localhost:8000 with:

- a big **GO SURF! / Maybe / Skip it** verdict and the best time to go
- wave height, period, wind and water temperature
- an hour-by-hour score for the rest of today and a look at the next 3 days

Data comes from the free [Open-Meteo](https://open-meteo.com) marine and weather APIs (no API key).
Scoring favours 0.4–1.0 m waves, 6+ s period, and light or easterly (offshore) wind.
Needs only Python 3 – no extra packages.
