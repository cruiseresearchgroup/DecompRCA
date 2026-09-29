# Microservice Platform — Operational System Documentation

**Asset:** A cloud-native microservice platform.
**Document scope:** Service inventory, request topology, and observability metrics for the platform.

---

## System Overview

The platform is an e-commerce system that handles end-to-end retail flows for an online retailer — svc11 browsing, cart management, svc12 authentication, checkout, svc04, and asynchronous svc02 dispatch. The application is implemented as a polyglot microservice system (Node.js, Java, Go, Erlang) with each service deployed independently on Kubernetes alongside its persistent stores (MySQL, MongoDB, Redis) and a RabbitMQ message broker.

The platform is composed of three classes of pods:

- **Application services** — stateless or lightly-stateful pods that serve svc12 traffic and orchestrate business logic.
- **Data-store pods** — every domain that owns persistent state runs its own database pod (`*-db`) co-deployed with the application service that owns it.
- **Messaging infrastructure** — a RabbitMQ broker and its exporter handle asynchronous svc02 dispatch.

All pods emit standard observability metrics — CPU usage, memory usage, request workload (rate), and response-latency percentiles — to a metrics historian. Channels follow the convention `{pod}_{metric_type}`.

---

## Application Services

| Pod | | Role | Calls |
|---|---|---|---|
| `svc09`    | Renders UI; orchestrates backend calls | all backend services |
| `svc08`       | Manages order creation and history     | svc02, svc04, svc10, svc12 |
| `svc11`    | Product svc11 (product listings)      | svc11-db |
| `svc10`        | Shopping cart management               | svc10-db |
| `svc12`         | User accounts and authentication       | svc12-db |
| `svc04`      | Payment processing (mock)              | none |
| `svc02`     | Shipping dispatch via RabbitMQ         | svc01 |
| `svc03` | Consumes svc02 queue from RabbitMQ  | svc01 |

---

## Data-Store Pods

| Pod | Type | Role |
|---|---|---|
| `svc11-db` | MySQL   | Persistent store for svc11 data |
| `svc10-db`     | MongoDB | Persistent store for cart data |
| `svc12-db`      | MongoDB | Persistent store for svc12 data |
| `svc08-db`    | MongoDB | Persistent store for svc08 |
| `svc07-db`   | Redis   | Session storage for `svc09` |

A database pod's CPU or memory anomaly is typically a downstream consequence of fault load on its owning application service. Conversely, an application service's latency anomaly may be caused by an underlying database pod (locking contention, disk pressure, slow query).

---

## Messaging Infrastructure

| Pod | Type | Role |
|---|---|---|
| `svc01`          | Erlang     | Message broker for asynchronous svc02 |
| `svc06` | Prometheus exporter | Scrapes broker statistics for the historian |

`svc02` publishes svc02-dispatch messages to `svc01`; `svc03` consumes them. A backlog or processing-rate anomaly therefore typically appears in `svc01` first, then in `svc03`.

---

## Request Topology

```
User → svc09
         ├── svc11 → svc11-db      (browse products)
         ├── svc12      → svc12-db           (login / register)
         ├── svc07-db                    (svc07 cookies)
         ├── svc10     → svc10-db          (add to cart)
         └── svc08                        (checkout)
               ├── svc12    → svc12-db
               ├── svc10   → svc10-db
               ├── svc04                 (charge)
               └── svc02 → svc01 → svc03
```

Checkout is the deepest transactional path: it touches authentication, cart, svc04, and the asynchronous svc02 pipeline.

---

## Metric Channel Reference

Each pod exposes a subset of the following metric channels in the historian, named `{pod}_{metric_type}`:

| Suffix | Description | Units | Typical coverage |
|---|---|---|---|
| `_cpu`        | CPU usage | millicores (m) | every pod |
| `_mem`        | Resident memory usage | MB | every application pod and database pod (except `svc11-db` and `svc06`, which only emit `_cpu`) |
| `_workload`   | Request rate / throughput | RPS | application services that receive HTTP traffic (`svc09`, `svc08`, `svc11`, `svc10`, `svc12`, `svc04`, `svc02`, `svc03`) |
| `_latency-50` | P50 request latency | seconds | HTTP-facing application services (same set as `_workload`) |
| `_latency-90` | P90 request latency | seconds | HTTP-facing application services (same set as `_workload`) |

Coverage notes:
- **HTTP-facing application services** (8 pods listed above) typically expose all five channels.
- **Database pods** (`svc11-db`, `svc10-db`, `svc12-db`, `svc08-db`, `svc07-db`) and **broker** (`svc01`) expose only `_cpu` / `_mem`. They don't serve HTTP traffic, so workload and latency aren't directly instrumented.
- **`svc11-db`** and **`svc06`** expose only `_cpu`.

**Example channel names:** `front-end_cpu`, `orders_latency-90`, `catalogue_workload`, `svc10-db_mem`, `rabbitmq_cpu`.
