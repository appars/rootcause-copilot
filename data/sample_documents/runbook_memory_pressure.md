# Runbook: Memory pressure and OOMKilled containers (FICTIONAL - training material)

## Symptoms
- `java.lang.OutOfMemoryError: Java heap space`
- Long `Full GC` pauses and heap usage close to 100%
- Kubernetes: `reason=OOMKilled`, `exit code 137`, `Back-off restarting failed container`
- Latency rises shortly before each crash

## Investigation steps
1. Plot heap usage over time between restarts. Steady growth suggests something is accumulating
   (cache, queue, leak); a sudden jump suggests a large request or batch.
2. Look for unbounded caches or collections in the logs (sizes that only go up).
3. Compare the JVM max heap with the container memory limit. The heap must leave room for
   non-heap memory (threads, metaspace, buffers).
4. If available, capture a heap dump. *Not available in the workshop simulation.*

## Mitigation options (approval required)
- Temporarily raise the memory limit (buys time, does not fix growth).
- Cap the cache size / add eviction.
- Roll back to the previous version if the growth started with a release.

## Do not
- Do not only raise limits without understanding the growth pattern.
