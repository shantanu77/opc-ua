# Using the OPC-UA Traffic Simulator

This guide shows how to pull and run the pre-built Docker image of the OPC-UA Traffic Simulator.

## Quick Start

### 1. Pull the Docker Image

```bash
docker pull shantanu77/opc-ua-simulator:v1.0
```

Or use the latest version:

```bash
docker pull shantanu77/opc-ua-simulator:latest
```

### 2. Run the Simulator

```bash
docker run -p 8000:8000 -p 4840:4840 --name opc-ua-sim shantanu77/opc-ua-simulator:v1.0
```

Or with Docker Compose (recommended):

Create a `docker-compose.yml` file:

```yaml
services:
  simulator:
    image: shantanu77/opc-ua-simulator:v1.0
    container_name: opc-ua-sim
    ports:
      - "8000:8000"
      - "4840:4840"
    restart: unless-stopped
```

Then run:

```bash
docker compose up -d
```

### 3. Access the Web Dashboard

Open your browser and navigate to:

```
http://localhost:8000
```

You should see the OPC-UA Traffic Simulator dashboard.

## Dashboard Features

### Control Panel
- **Start Simulator**: Begin generating traffic
- **Stop Simulator**: Stop the simulator
- **Save Config**: Save configuration changes

### Status Cards
- **State**: Current running status (Running/Stopped)
- **Uptime**: How long the simulator has been running
- **Total Ops**: Total operations performed
- **Ops/Sec**: Current operations per second
- **Client Rate**: Effective client operations rate (with load profiles)
- **Errors**: Total errors encountered
- **Node Updates**: Number of tag/node updates
- **Remaining Run Time**: Time left for timed runs (if configured)

### Configuration Sections

#### Simulator Configuration
- **Endpoint**: OPC-UA server endpoint (default: `opc.tcp://0.0.0.0:4840/freeopcua/server/`)
- **Namespace URI**: XML namespace for tags
- **Node Count**: Number of simulated tags/nodes
- **Update Interval (ms)**: How often to update tag values
- **Jitter (ms)**: Random variation in update timing
- **Pattern**: Value generation pattern
  - `random`: Random values
  - `sine`: Sine wave oscillation
  - `sawtooth`: Sawtooth wave
  - `random_walk`: Gaussian random walk
  - `burst`: Bursty traffic with spikes
- **Min/Max Value**: Value range for tags
- **Noise Amplitude**: Random noise added to values
- **Burst Probability**: Probability of a burst (for burst pattern)
- **Burst Multiplier**: How much to multiply during bursts
- **Random Seed**: Reproducible random sequence

#### Traffic and Fault Controls
- **Virtual Clients**: Number of simulated OPC-UA clients
- **Client Ops/Sec**: Operations per second per client
- **Run Duration (minutes)**: How long to run before auto-stop (0 = unlimited)
- **Load Profile**: Traffic increase strategy
  - `constant`: Fixed traffic rate
  - `linear_ramp`: Smoothly increase to target rate
  - `step_ramp`: Increase in discrete steps
  - `spike_wave`: Periodic traffic spikes
- **Ramp Target Ops/Sec**: Target rate for ramp profiles
- **Ramp Duration (minutes)**: How long to reach target
- **Step Interval (seconds)**: Time between steps (step_ramp)
- **Step Increment Ops/Sec**: Amount to increase per step
- **Spike Every (seconds)**: Frequency of spikes (spike_wave)
- **Spike Multiplier**: How much to multiply during spikes
- **Traffic Mix Ratios**:
  - `Read Ratio`: Percentage of read operations
  - `Write Ratio`: Percentage of write operations
  - `Browse Ratio`: Percentage of browse operations
  - `Subscribe Ratio`: Percentage of subscribe operations
  - **Note**: These must sum to exactly 1.00
- **Fault Injection**: Enable/disable fault injection
- **Fault Error Rate**: Probability of injecting errors

### Real-Time Monitoring

#### Traffic Timeline Chart
- **Ops Last Sec**: Operations completed in the last second (green)
- **Errors Last Sec**: Errors in the last second (red)
- Shows last 40 seconds of data

#### Event Log
- Real-time log of simulator events
- Shows timestamps, log level (INFO/ERROR), and message
- Displays last 80 events
- Color-coded: green for INFO, red for ERROR

#### Per-Operation Counters
- **Read Ops**: Total read operations
- **Write Ops**: Total write operations
- **Browse Ops**: Total browse operations
- **Subscribe Ops**: Total subscribe operations

## Common Use Cases

### Scenario 1: Continuous Soak Test (30 minutes)
1. Set **Run Duration** to `30`
2. Set **Load Profile** to `constant`
3. Set **Virtual Clients** to `8`
4. Set **Client Ops/Sec** to `10`
5. Click **Start Simulator**
6. Monitor metrics until auto-stop

### Scenario 2: Load Ramp Test (5 to 50 ops/sec over 10 minutes)
1. Set **Virtual Clients** to `10`
2. Set **Client Ops/Sec** to `5`
3. Set **Load Profile** to `linear_ramp`
4. Set **Ramp Target Ops/Sec** to `50`
5. Set **Ramp Duration (minutes)** to `10`
6. Set **Run Duration** to `10`
7. Click **Start Simulator**
8. Watch the **Client Rate** card increase smoothly

### Scenario 3: Spike Wave Test (periodic traffic bursts)
1. Set **Virtual Clients** to `4`
2. Set **Client Ops/Sec** to `10`
3. Set **Load Profile** to `spike_wave`
4. Set **Spike Every (seconds)** to `30`
5. Set **Spike Multiplier** to `3.0`
6. Click **Start Simulator**
7. Observe spikes in the chart every 30 seconds

### Scenario 4: Fault Injection Test
1. Configure normal traffic (e.g., 4 clients, 8 ops/sec)
2. Enable **Fault Injection**
3. Set **Fault Error Rate** to `0.1` (10% error rate)
4. Click **Start Simulator**
5. Monitor **Errors** card to see fault injection in action

## API Endpoints

If you want to control the simulator programmatically:

```bash
# Get current configuration
curl http://localhost:8000/api/simulator/config

# Update configuration
curl -X PUT http://localhost:8000/api/simulator/config \
  -H "Content-Type: application/json" \
  -d '{"virtual_clients": 8, "client_ops_per_sec": 10}'

# Start simulator
curl -X POST http://localhost:8000/api/simulator/start

# Stop simulator
curl -X POST http://localhost:8000/api/simulator/stop

# Get current status
curl http://localhost:8000/api/simulator/status

# Get metrics
curl http://localhost:8000/api/simulator/metrics

# Get event log
curl http://localhost:8000/api/simulator/events
```

## Ports and Network

The simulator exposes two ports:

- **8000**: Web dashboard and REST API
- **4840**: OPC-UA server endpoint

To allow remote OPC-UA clients to connect:

```bash
docker run -p 0.0.0.0:8000:8000 -p 0.0.0.0:4840:4840 shantanu77/opc-ua-simulator:v1.0
```

To connect from another machine, use the host's IP address or hostname:

```
opc.tcp://HOSTNAME_OR_IP:4840/freeopcua/server/
```

## Stopping the Simulator

### With Docker run:
```bash
docker stop opc-ua-sim
docker rm opc-ua-sim
```

### With Docker Compose:
```bash
docker compose down
```

## Troubleshooting

### Container won't start
Check logs:
```bash
docker logs opc-ua-sim
```

### Port already in use
Use different ports:
```bash
docker run -p 9000:8000 -p 5840:4840 shantanu77/opc-ua-simulator:v1.0
```

Then access at `http://localhost:9000`

### Web dashboard not loading
- Ensure port 8000 is accessible
- Check firewall settings
- Verify container is running: `docker ps`

### OPC-UA clients can't connect
- Ensure port 4840 is open
- Check that simulator is running
- Verify endpoint in simulator config matches what clients expect

## Performance Tips

- For high-load testing, increase **Virtual Clients** and **Client Ops/Sec**
- Start low and increase gradually to avoid overload
- Monitor system resources (CPU, memory) while running
- Use a timed run (**Run Duration**) to avoid infinite tests

## Documentation

For more details, see:
- `spec.md`: Feature specification and design
- `README.md`: Project overview and development setup
