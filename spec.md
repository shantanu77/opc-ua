# OPC-UA simulator requirements

- Exclusive XML and manual tag sources.
- XML mode imports data nodes and engineering metadata; applies embedded JSON rules.
- Manual mode generates tags with configured ranges, patterns and update timing.
- Preview shows effective values, parameters, ranges and rule source before starting.
- One OPC-UA listener for external clients; no internal client traffic generation.
- Live table reads actual OPC-UA values; metrics track producer updates and errors.
- Source changes and validated uploads occur only while stopped.
- Docker exposes the dashboard on 8000 and OPC-UA on 4840.
