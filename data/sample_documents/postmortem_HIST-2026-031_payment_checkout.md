# Post-incident review: HIST-2026-031 (FICTIONAL - training material)

**Service:** payment-service  **Severity:** SEV1  **Duration:** 25 minutes  **Date:** 14 Oct 2026

## What happened
During the morning peak, checkout requests began failing with HTTP 503 after ~30 seconds.
The connection pool of payment-service showed `active=20 idle=0` with many waiting requests.

## Contributing factors
- A month-end reporting export ran on the same connection pool as checkout traffic.
- Its queries took 10-25 seconds each and held connections for the whole duration.
- There was no statement timeout.

## Resolution
- Paused the export; rolling restart of payment-service released held connections.
- Follow-up: reporting moved to the read replica, statement timeout of 5 s added,
  alert added on the pool `waiting` metric.

## Lessons learned
- Latency alerts fired late; the pool `waiting` metric would have warned 10 minutes earlier.
- Keep batch work away from the transactional pool.
