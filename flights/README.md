# Flight Search

Find the cheapest flights between countries, including multi-leg routes with configurable layovers.

## How It Works

- Search by **country, city, or airport** — enter "Israel" and it searches all Israeli airports
- Specify a **date range** for departure
- Configure **stopover preferences**: max stops, min/max layover time
- Results sorted by **price**, showing full route details
- Direct links to **Google Flights** and **airline websites** for each leg
- Discovers **multi-leg routes** (e.g., Israel → Cyprus → Scotland) that may be cheaper than direct flights

## Data Source

Uses the [Kiwi.com Tequila API](https://tequila.kiwi.com/) which:
- Aggregates flight data from 150+ airlines
- Supports **virtual interlining** — combines different airlines into routes you won't find elsewhere
- Provides actual bookable prices
- Is free to use (requires API key registration)

## Setup

1. Get a free API key at [tequila.kiwi.com](https://tequila.kiwi.com/)
2. Run the server:

```bash
TEQUILA_API_KEY=your_key_here node server.js
```

3. Open http://localhost:3001

## Usage

1. Type your departure location (country, city, or airport) and select from the dropdown
2. Type your destination and select from the dropdown
3. Set your departure date range
4. Adjust stopover settings:
   - **Max stopovers**: 0 for direct only, up to 3
   - **Min layover**: minimum connection time (e.g., 2 hours for comfort)
   - **Max layover**: maximum layover allowed (e.g., 12 hours, or 48 hours if you want to explore a stopover city)
5. Click Search
6. Results show price, route, airlines, and layover details
7. Click "Details" to see each flight leg with individual Google Flights and airline website links

## Example Use Case

Want to fly from Israel to Scotland cheaply?

1. Set "From" to **Israel** (searches all airports: TLV, ETH, etc.)
2. Set "To" to **Scotland** or **United Kingdom**
3. Set max stopovers to 2, max layover to 24 hours
4. The app will find routes like:
   - TLV → LCA (Cyprus) → EDI — via Wizz Air + Ryanair
   - TLV → FCO (Rome) → EDI — via Wizz Air + easyJet
   - TLV → MLA (Malta) → EDI — via Ryanair connections

Each result links to the actual airline websites so you can verify and book at source.

## Requirements

- Node.js (no external dependencies)
- Free Kiwi.com Tequila API key
