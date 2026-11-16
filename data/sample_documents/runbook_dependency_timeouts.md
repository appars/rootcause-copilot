# Runbook: Downstream dependency timeouts (FICTIONAL - training material)

## Symptoms
- `Read timed out`, `request to http://<dependency> timed out after Nms`
- Retry messages (`retrying attempt 2/3`) followed by `retries exhausted`
- HTTP 504 from your own API, latency close to timeout x number of attempts
- Worker / thread pool saturation (`active=50/50 queue=...`)

## Why retries can make it worse
If a dependency is slow, every retry adds more load to it and keeps your own threads busy longer.
3 attempts x 5 s timeout = 15 s per request. With limited worker threads, healthy requests queue
behind the slow ones (a *retry storm*).

## Investigation steps
1. Identify the dependency and when timeouts started.
2. Calculate worst-case latency: `timeout x attempts`.
3. Check the dependency's own health and *its* dependencies.
4. Check whether a circuit breaker or fallback exists.

## Mitigation options (change via Git; approval required)
- Reduce retries and use exponential backoff with jitter.
- Lower the timeout to a value that matches the user-facing SLO.
- Enable a circuit breaker and a fallback (cached or default response).
- Coordinate with the owning team of the dependency.
