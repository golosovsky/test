const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');
const url = require('url');

const PORT = process.env.PORT || 3001;
const TEQUILA_API_KEY = process.env.TEQUILA_API_KEY || '';
const TEQUILA_BASE = 'https://api.tequila.kiwi.com';

function tequilaRequest(endpoint, params) {
  return new Promise((resolve, reject) => {
    const qs = new URLSearchParams(params).toString();
    const fullUrl = `${TEQUILA_BASE}${endpoint}?${qs}`;

    const parsed = new URL(fullUrl);
    const options = {
      hostname: parsed.hostname,
      path: parsed.pathname + parsed.search,
      method: 'GET',
      headers: {
        'apikey': TEQUILA_API_KEY,
        'Accept': 'application/json',
      },
    };

    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', (chunk) => { data += chunk; });
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, data: JSON.parse(data) });
        } catch (e) {
          reject(new Error(`Failed to parse response: ${data.slice(0, 200)}`));
        }
      });
    });

    req.on('error', reject);
    req.setTimeout(30000, () => {
      req.destroy();
      reject(new Error('Request timeout'));
    });
    req.end();
  });
}

async function handleLocationSearch(query) {
  const res = await tequilaRequest('/locations/query', {
    term: query,
    locale: 'en-US',
    location_types: 'country,city,airport',
    limit: 20,
    active_only: true,
  });
  if (res.status !== 200) {
    return { error: 'Location search failed', details: res.data };
  }
  const locations = (res.data.locations || []).map((loc) => ({
    id: loc.id,
    name: loc.name,
    code: loc.code,
    type: loc.type,
    country: loc.country ? loc.country.name : '',
    countryCode: loc.country ? loc.country.code : '',
    city: loc.city ? loc.city.name : '',
    airports: loc.type === 'country' || loc.type === 'city'
      ? (loc.airports || []).map((a) => ({ id: a.id, name: a.name, code: a.code || a.id }))
      : undefined,
  }));
  return { locations };
}

async function handleFlightSearch(params) {
  const {
    fly_from, fly_to,
    date_from, date_to,
    max_stopovers,
    stopover_from, stopover_to,
    adults, curr, limit, sort,
  } = params;

  if (!fly_from || !fly_to || !date_from || !date_to) {
    return { error: 'Missing required parameters: fly_from, fly_to, date_from, date_to' };
  }

  const searchParams = {
    fly_from,
    fly_to,
    date_from,
    date_to,
    flight_type: 'oneway',
    adults: adults || '1',
    curr: curr || 'EUR',
    locale: 'en',
    limit: limit || '40',
    sort: sort || 'price',
    max_stopovers: max_stopovers || '2',
    vehicle_type: 'aircraft',
  };

  // Stopover duration configuration (in hours, format like "2:00")
  if (stopover_from) searchParams.stopover_from = stopover_from;
  if (stopover_to) searchParams.stopover_to = stopover_to;

  const res = await tequilaRequest('/v2/search', searchParams);
  if (res.status !== 200) {
    return { error: 'Flight search failed', details: res.data };
  }

  const flights = (res.data.data || []).map((flight) => {
    const legs = (flight.route || []).map((leg) => ({
      airline: leg.airline,
      airlineName: leg.airline,
      flightNo: `${leg.airline}${leg.flight_no}`,
      from: {
        airport: leg.flyFrom,
        city: leg.cityFrom,
        country: leg.countryFrom ? leg.countryFrom.name : '',
      },
      to: {
        airport: leg.flyTo,
        city: leg.cityTo,
        country: leg.countryTo ? leg.countryTo.name : '',
      },
      departure: leg.local_departure,
      arrival: leg.local_arrival,
      durationSeconds: leg.flight_duration || 0,
    }));

    // Calculate layover times between legs
    const layovers = [];
    for (let i = 0; i < legs.length - 1; i++) {
      const arrivalTime = new Date(legs[i].arrival).getTime();
      const nextDepartureTime = new Date(legs[i + 1].departure).getTime();
      const layoverMs = nextDepartureTime - arrivalTime;
      layovers.push({
        airport: legs[i].to.airport,
        city: legs[i].to.city,
        country: legs[i].to.country,
        durationMinutes: Math.round(layoverMs / 60000),
      });
    }

    return {
      id: flight.id,
      price: flight.price,
      currency: flight.currency || params.curr || 'EUR',
      legs,
      layovers,
      totalDurationSeconds: flight.duration ? flight.duration.total : 0,
      stops: legs.length - 1,
      bookingLink: flight.deep_link,
      availableSeats: flight.availability ? flight.availability.seats : null,
      airlines: [...new Set((flight.route || []).map((r) => r.airline))],
      cityFrom: flight.cityFrom,
      cityTo: flight.cityTo,
      countryFrom: flight.countryFrom ? flight.countryFrom.name : '',
      countryTo: flight.countryTo ? flight.countryTo.name : '',
    };
  });

  return {
    flights,
    totalResults: res.data.data ? res.data.data.length : 0,
    searchId: res.data.search_id,
    currency: params.curr || 'EUR',
  };
}

function serveStatic(filePath, res) {
  const ext = path.extname(filePath);
  const contentTypes = {
    '.html': 'text/html',
    '.js': 'application/javascript',
    '.css': 'text/css',
    '.json': 'application/json',
    '.png': 'image/png',
    '.ico': 'image/x-icon',
  };

  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      res.end('Not Found');
      return;
    }
    res.writeHead(200, { 'Content-Type': contentTypes[ext] || 'text/plain' });
    res.end(data);
  });
}

const server = http.createServer(async (req, res) => {
  const parsed = url.parse(req.url, true);
  const pathname = parsed.pathname;

  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  // API routes
  if (pathname === '/api/locations') {
    try {
      const query = parsed.query.q;
      if (!query) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Missing query parameter q' }));
        return;
      }
      const result = await handleLocationSearch(query);
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(result));
    } catch (err) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: err.message }));
    }
    return;
  }

  if (pathname === '/api/search') {
    try {
      if (!TEQUILA_API_KEY) {
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
          error: 'API key not configured. Set the TEQUILA_API_KEY environment variable.',
          help: 'Get a free API key at https://tequila.kiwi.com/',
        }));
        return;
      }
      const result = await handleFlightSearch(parsed.query);
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(result));
    } catch (err) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: err.message }));
    }
    return;
  }

  if (pathname === '/api/status') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      apiConfigured: !!TEQUILA_API_KEY,
      help: TEQUILA_API_KEY
        ? 'API key is configured. Ready to search.'
        : 'Set TEQUILA_API_KEY env variable. Get a free key at https://tequila.kiwi.com/',
    }));
    return;
  }

  // Static files
  if (pathname === '/' || pathname === '/index.html') {
    serveStatic(path.join(__dirname, 'index.html'), res);
    return;
  }

  // Fallback
  res.writeHead(404, { 'Content-Type': 'text/plain' });
  res.end('Not Found');
});

server.listen(PORT, () => {
  console.log(`Flight Search running at http://localhost:${PORT}`);
  if (!TEQUILA_API_KEY) {
    console.log('');
    console.log('WARNING: No TEQUILA_API_KEY set.');
    console.log('Get a free API key at https://tequila.kiwi.com/');
    console.log('Then run: TEQUILA_API_KEY=your_key node server.js');
  }
});
