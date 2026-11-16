# Runbook: Database connection problems (FICTIONAL - training material)

**Applies to:** Java/Spring services using HikariCP (payment-service, order-service, ...).

## Symptoms you may see
- `SQLTransientConnectionException: ... Connection is not available, request timed out after 30000ms`
- Pool stats with `idle=0` and a growing `waiting` count
- Requests failing after ~30 seconds (the connection timeout), often returned as HTTP 503
- Health check `db=UP` but with a very slow validation query

## Investigation steps
1. Compare pool `active`, `idle` and `waiting` over time. A pool that stays at `active=max, idle=0` is saturated.
2. Look for *what is holding connections*: slow queries, batch/report jobs, long transactions, connection leaks.
3. Check whether the slow queries started **before** the errors (cause) or **after** (effect).
4. Check database-side metrics (active sessions, locks, CPU). *Not available in the workshop simulation.*
5. Rule out memory/CPU pressure in the application (heap, GC, CPU usage).

## Mitigation options (all require approval in production)
- Pause or reschedule batch/reporting jobs that share the pool.
- Rolling restart of the service to release stuck connections (temporary relief only).
- Increase the pool size **only** if the database can handle more sessions.
- Add statement timeouts so one slow query cannot hold a connection for minutes.

## Do not
- Do not raise the pool size blindly - you may overload the database and make things worse.
- Do not restart all replicas at the same time.
