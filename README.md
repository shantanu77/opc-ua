# OPC-UA Traffic Simulator

A full Python OPC-UA simulator with a live frontend dashboard to create test traffic for OPC-UA systems.

## Features
- Embedded OPC-UA server with configurable endpoint and namespace.
- Configurable tag count and value generation patterns.
- Virtual OPC-UA clients generating read/write/browse/subscribe traffic.
- Timed continuous runs (set test duration in minutes with auto-stop).
- Dynamic load profiles: constant, linear ramp, step ramp, and spike wave.
- Fault injection (bad-node reads and operation error rate).
- Live dashboard with metrics, charts, operation counters, and logs.

## Stack
- Backend: FastAPI + asyncua
- Frontend: Vue 3 + Chart.js

## Project Structure
- `spec.md`: simulator specification
- `app/main.py`: FastAPI application and API routes
- `app/simulator.py`: OPC-UA server and traffic simulation engine
- `app/schemas.py`: Pydantic request/response and config models
- `app/static/index.html`: dashboard UI
- `app/static/app.js`: frontend logic
- `app/static/styles.css`: frontend styling

## Install
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open:
- http://localhost:8000

## Docker

Build image:
```bash
docker build -t opc-ua-simulator:latest .
```

Run container:
```bash
docker run --rm -p 8000:8000 -p 4840:4840 --name opc-ua-simulator opc-ua-simulator:latest
```

Using Docker Compose:
```bash
docker compose up --build
```

## API Endpoints
- `GET /api/simulator/config`
- `PUT /api/simulator/config`
- `POST /api/simulator/start`
- `POST /api/simulator/stop`
- `GET /api/simulator/status`
- `GET /api/simulator/metrics`
- `GET /api/simulator/events`

## Notes
- This simulator is intended for test and QA environments.
- Use realistic client counts and operation rates for load testing.
- Keep traffic ratios summing to exactly `1.0`.
- Set `test_duration_minutes` to `0` for unlimited runs.
