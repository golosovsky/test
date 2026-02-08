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
