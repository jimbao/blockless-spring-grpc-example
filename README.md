# blockless-spring-grpc-example

A Spring Boot + gRPC demo app showing [blockless](https://github.com/pjlabs/blockless) in action, with real Postgres for benchmarking.

## What it demonstrates

| RPC | Blockless feature | What it proves |
|---|---|---|
| `Greet` | `Blockless.get()` | Wait for a downstream result; ordinary platform callers still block |
| `GreetAll` | `Parallel.map()` + `withMaxConcurrency(5)` | Bounded parallel fan-out with gRPC + MDC context propagation |
| `GreetSafe` | `Parallel.toEither()` | Partial failure handling — some succeed, some fail, results stay in order |
| `Query` | direct vs waiting Blockless vs experimental continuations | Compare bounded PT execution, suspended PT execution, and VT execution on real DB queries |
| `FanOut` | `Parallel.map()` vs serial | Benchmark: compare serial vs parallel fan-out on real DB |

## Setup

Requires Docker, Java 21+, Maven.

```sh
# Build the experimental API (not yet published to Maven Central).
git clone https://github.com/jimbao/blockless.git /tmp/blockless-native
git -C /tmp/blockless-native checkout 6425e3452db3923d647cf7a743b3068bc42be0f3
mvn -f /tmp/blockless-native/pom.xml -DskipTests install

# Start Postgres
docker compose up -d

# Start the app (gRPC on port 9090, Postgres on 5433)
mvn spring-boot:run -Dfmt.skip=true
```

## Try it

Requires [grpcurl](https://github.com/fullstorydev/grpcurl).

### GreetingService

```sh
grpcurl -plaintext -d '{"name": "Toothless"}' localhost:9090 org.pjlabs.example.GreetingService/Greet

grpcurl -plaintext -d '{"names": ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"]}' localhost:9090 org.pjlabs.example.GreetingService/GreetAll

grpcurl -plaintext -d '{"names": ["Alpha", "FAIL", "Gamma"]}' localhost:9090 org.pjlabs.example.GreetingService/GreetSafe

grpcurl -plaintext -H 'trace-id: dragon-trace-789' -d '{"names": ["A", "B", "C"]}' localhost:9090 org.pjlabs.example.GreetingService/GreetAll
```

### BenchmarkService

**Single query — join vs blockless:**
```sh
# Direct call (default gRPC handler thread)
grpcurl -plaintext -d '{"mode": "join", "country": "SE", "sleep_seconds": 0.05}' localhost:9090 org.pjlabs.example.BenchmarkService/Query

# Blockless.get() — runs query on a virtual thread
grpcurl -plaintext -d '{"mode": "blockless", "country": "SE", "sleep_seconds": 0.05}' localhost:9090 org.pjlabs.example.BenchmarkService/Query

# Force handler onto a PT or VT
grpcurl -plaintext -d '{"mode": "blockless", "thread_type": "pt", "country": "SE", "sleep_seconds": 0.05}' localhost:9090 org.pjlabs.example.BenchmarkService/Query

grpcurl -plaintext -d '{"mode": "blockless", "thread_type": "vt", "country": "SE", "sleep_seconds": 0.05}' localhost:9090 org.pjlabs.example.BenchmarkService/Query
```

**Fan-out — serial vs parallel:**
```sh
# Serial (one query at a time)
grpcurl -plaintext -d '{"mode": "serial", "countries": ["SE","US","GB","DE","JP"], "sleep_seconds": 0.05}' localhost:9090 org.pjlabs.example.BenchmarkService/FanOut

# Parallel (all queries at once)
grpcurl -plaintext -d '{"mode": "parallel", "countries": ["SE","US","GB","DE","JP"], "sleep_seconds": 0.05}' localhost:9090 org.pjlabs.example.BenchmarkService/FanOut

# Parallel with bounded concurrency
grpcurl -plaintext -d '{"mode": "parallel", "countries": ["SE","US","GB","DE","JP"], "sleep_seconds": 0.05, "max_concurrency": 3}' localhost:9090 org.pjlabs.example.BenchmarkService/FanOut
```

### Experimental continuation query

The new mode is available on the **gRPC Query RPC**. It runs the same
`Blockless.get()` database call inside `Continuations.run`, allowing a platform
worker to return to its executor while the query runs on a virtual thread:

```sh
grpcurl -plaintext -d '{"mode":"continuation","thread_type":"pt","pt_pool_size":4,"db_pool_size":10,"country":"SE","sleep_seconds":0.01}' localhost:9090 org.pjlabs.example.BenchmarkService/Query
```

The gRPC reply is sent after resumption, and asynchronous query failures terminate
the RPC with `INTERNAL`. gRPC and MDC context propagators are installed around
the continuation. This is experimental and requires the pinned library revision
above. The continuation adapter is maintained in Blockless and has no third-party
runtime dependencies. No annotations, bytecode enhancer, or Java agent are needed.

`mvn spring-boot:run` and the test JVM are configured with the required export.
When launching the packaged jar yourself, include it explicitly:

```sh
java --add-exports=java.base/jdk.internal.vm=ALL-UNNAMED -Xms512m -Xmx512m \
  -XX:ActiveProcessorCount=2 -jar target/blockless-spring-grpc-example-0.1.0-SNAPSHOT.jar
```

The HTTP endpoints retain their original modes; they do not expose the new
continuation mode. Direct blocking work, `Parallel.map`, and ordinary calls outside
a continuation boundary retain their normal waiting behavior.

### Compare continuation performance

With the app and Postgres running, install
[`ghz` v0.120.0](https://github.com/bojand/ghz/releases/tag/v0.120.0) and run:

```sh
python3 benchmarks/continuations.py
```

This compares `join`, waiting `blockless`, and `continuation` on both PT and VT
handlers in the same application. Settings: PT pool 4, DB pool 10, 32 concurrent
requests, 4 gRPC connections, and 10 ms `pg_sleep`. Five repetitions reverse
scenario order on alternate runs; each case gets 1s warmup and 3s measurement.
The report prints median requests/s, median p95 with its range, and errors.
Latency is measured by the gRPC client and includes executor queueing; the
reply's internal `elapsed_ms` field starts after dispatch and excludes queueing.
Raw ghz output and settings are saved under ignored `results/continuations/`.
Any RPC error fails the run. Treat shared-machine numbers as workload-specific;
compare the native PT result with the ordinary VT control as well as the PT baseline.

To expose the database pool limit, restart the app with
`--spring.datasource.hikari.maximum-pool-size=4`, then repeat with the same PT
and DB capacity. Restarting avoids measuring old connections left over from a
larger pool:

```sh
python3 benchmarks/continuations.py --db-pool-size 4 --output results/continuations-db4
```

### Benchmark parameters

| Parameter | Values | Description |
|---|---|---|
| `mode` | `join`, `blockless`, `continuation` (gRPC Query) / `serial`, `parallel` (FanOut) | Which approach to use |
| `thread_type` | `pt`, `vt`, empty | Query handler type; continuation defaults to the PT pool, other modes default to the gRPC handler |
| `country` | any seeded country | `SE`, `US`, `GB`, `DE`, `JP`, `BR`, `IN`, `AU` |
| `sleep_seconds` | float | pg_sleep per query (simulates I/O latency) |
| `max_concurrency` | int | Limit parallel tasks (FanOut only, 0 = unbounded) |
| `pt_pool_size` | int | PT handler pool size (Query only, 0 = availableProcessors) |
| `db_pool_size` | int | HikariCP max pool size (Query only, 0 = keep current, default 10) |

### HTTP endpoints (for JMeter)

The original query and fan-out modes are exposed as HTTP GET on port 8080.
Experimental continuation mode is available only on the gRPC Query RPC.

**Single query:**
```sh
curl 'http://localhost:8080/benchmark/query?mode=join&country=SE&sleepSeconds=0.05'
curl 'http://localhost:8080/benchmark/query?mode=blockless&country=SE&sleepSeconds=0.05'
curl 'http://localhost:8080/benchmark/query?mode=blockless&threadType=pt&ptPoolSize=10&country=SE&sleepSeconds=0.05'
curl 'http://localhost:8080/benchmark/query?mode=blockless&threadType=vt&country=SE&sleepSeconds=0.05'
curl 'http://localhost:8080/benchmark/query?mode=join&dbPoolSize=5&country=SE&sleepSeconds=0.05'
```

**Fan-out:**
```sh
curl 'http://localhost:8080/benchmark/fanout?mode=serial&countries=SE,US,GB,DE,JP&sleepSeconds=0.05'
curl 'http://localhost:8080/benchmark/fanout?mode=parallel&countries=SE,US,GB,DE,JP&sleepSeconds=0.05'
curl 'http://localhost:8080/benchmark/fanout?mode=parallel&countries=SE,US,GB,DE,JP&sleepSeconds=0.05&maxConcurrency=3'
```

## Load testing with JMeter

Each JMeter thread sends one HTTP request — N threads = N concurrent requests.

Example test matrix:

| JMeter threads | URL | What it tests |
|---|---|---|
| 200 | `/benchmark/query?mode=join` | Baseline: direct DB call |
| 200 | `/benchmark/query?mode=blockless` | Blockless.get() |
| 200 | `/benchmark/query?mode=join&threadType=pt&ptPoolSize=10` | PT handler (10) + direct |
| 200 | `/benchmark/query?mode=blockless&threadType=pt&ptPoolSize=10` | PT handler (10) + Blockless |
| 200 | `/benchmark/query?mode=join&threadType=vt` | VT handler + direct |
| 200 | `/benchmark/query?mode=blockless&threadType=vt` | VT handler + Blockless |
| 200 | `/benchmark/fanout?mode=serial` | Serial fan-out |
| 200 | `/benchmark/fanout?mode=parallel` | Parallel fan-out |

## Tests

```sh
docker compose up -d
mvn verify
```

Tests cover:
- `Blockless.get()` round-trip
- Native continuation queries against real Postgres, including a second RPC
  completing on a single platform worker while the first query is still sleeping
- PT/VT result parity and asynchronous failure delivery
- `Parallel.map()` fan-out correctness and parallelism (5 x 100ms in <400ms)
- `Parallel.toEither()` partial failure and all-success cases
- MDC traceId propagation from gRPC header to each virtual thread

Benchmark IT (requires Docker):
```sh
mvn test -Dtest=BlocklessBenchmarkIT
```

## Requirements

- Java 21+
- Maven
- Docker (for Postgres)

## License

Apache 2.0

## Performance comparisons

The **Performance comparison** workflow compares latest `main` with the proposed
PR merge. It updates one PR comment and publishes a summary with raw artifacts;
fork runs publish the summary and artifacts only. After merging the workflow,
use **Run workflow** with a PR number to rerun against updated `main`.

Six gRPC scenarios cover direct/Blockless queries on PT/VT handlers and
serial/bounded-parallel fan-out. Fixed settings: Java 21, Postgres 18.1, 1 ms I/O,
DB pool 10, PT pool 4, 32 concurrent requests, and 4 client connections.
Five repetitions alternate base/candidate order with fresh app/database instances;
each scenario gets 1s warmup and 3s measurement. Expected runtime: about 8 minutes.

The compact report shows median throughput, p95 latency with run ranges, and
errors. Raw ghz JSON retains all percentiles. Results are informational; compare
changes with run variation and the direct/serial controls before judging a regression.
Build or benchmark failures still fail CI. Shared-runner results describe these
workloads; the short windows favor finding larger regressions over precise
sub-percent comparisons.
