# Microservice Platform — Operational System Documentation

**Asset:** A cloud-native microservice platform.
**Document scope:** Service inventory, request topology, and observability metrics for the platform.

---

## System Overview

The platform is a travel-booking system that handles end-to-end travel booking for both high-speed and normal-speed rail networks — search, ticket reservation, payment, cancellation, refund, rebooking, and trip-time add-ons such as in-trip food and travel insurance. The application is implemented as a polyglot microservice system (Java/Spring, Node.js, Python, Go) with each service deployed independently on Kubernetes.

The platform is composed of two classes of pods:

- **Application services** — stateless or lightly-stateful pods that serve user traffic and orchestrate business logic. Each application service is responsible for one functional domain (e.g., seat allocation, payment processing, order management).
- **Data-store pods** — every domain that owns persistent state runs its own dedicated database pod (MongoDB, with one MySQL store), co-deployed with the application service that owns it. Database pods receive read/write traffic from their owning application service and emit their own observability metrics.

All pods emit standard observability metrics — CPU usage, memory usage, request workload (rate), and response-latency percentiles — to a metrics historian. Channels follow the convention `{pod}_{metric_type}`; all pod names share the prefix `ts-`, e.g., `ts-travel-service_cpu`, `ts-order-service_latency-90`, `ts-travel-mongo_mem`.

---

## Application Services

### User-Facing / Entry Points
| Pod | Role |
|---|---|
| `svc10` | Main web UI; aggregates all user-facing flows |
| `ts-gateway-service` | API gateway; routes frontend requests to backend |

### Travel & Search Domain
| Pod | Role |
|---|---|
| `svc37` | High-speed trips routes (G/D trips) |
| `svc38` | Normal-speed trips routes (Z/T/K trips) |
| `svc09` | Route definitions |
| `svc49` | Multi-leg route planning |
| `svc05` | Station information |
| `svc62` | Train type information |
| `svc35` | System-wide configuration |

### Booking & Order Domain
| Pod | Role |
|---|---|
| `svc21` | Orders for high-speed trips |
| `svc15` | Orders for normal-speed trips |
| `svc34` | Seat availability and reservation |
| `svc43` | Basic order info (fares, trips info) |
| `svc11` | Ticket information queries |
| `svc51` | Ticket-office storefront |

### Payment & Finance Domain
| Pod | Role |
|---|---|
| `svc26` | Internal payment processing |
| `svc12` | External payment gateway |
| `svc23` | Fare calculation |

### User & Auth Domain
| Pod | Role |
|---|---|
| `svc40` | User account management |
| `svc02` | Authentication and token management |
| `svc50` | Email verification codes |
| `svc60` | Saved passenger contacts |
| `svc27` | User avatar storage |

### Trip Management Domain
| Pod | Role |
|---|---|
| `svc36` | Ticket-booking orchestrator (high-speed) |
| `svc07` | Ticket-booking orchestrator (normal-speed) |
| `svc52` | Ticket cancellation |
| `svc19` | Ticket rebooking |
| `svc31` | Trip execution status updates |
| `svc13` | Multi-trip planning |

### Add-on Services
| Pod | Role |
|---|---|
| `svc39` | In-trip food ordering |
| `svc24` | Food provider mapping by terminals |
| `svc04` | Travel insurance |
| `svc55` | Baggage consignment |
| `svc25` | Baggage price calculation |
| `svc14` | Security checks on bookings |

### Administrative & Notification
| Pod | Role |
|---|---|
| `svc64` | Admin configuration |
| `svc30` | Admin order management |
| `svc48` | Admin route management |
| `svc46` | Admin travel management |
| `svc44` | Admin user management |
| `svc32` | News / promotions display |
| `svc63` | Email / SMS notifications |
| `svc01` | Discount vouchers |

---

## Data-Store Pods

Each domain that owns persistent state has its own database pod following the naming pattern `ts-{domain}-mongo` (or `svc06` for the only MySQL store). These pods receive read/write traffic from their owning application service and emit their own CPU and memory metrics.

```
svc33         svc18            svc17
svc41              svc56      svc58
svc42            svc20          svc29
svc53           svc59            svc57
svc22     svc61            svc54
svc08          svc03         svc47
svc28              svc16         svc06
svc45
```

A database pod's CPU or memory anomaly is typically a downstream consequence of fault load on its owning application service. Conversely, an application service's latency anomaly may be caused by an underlying database pod (locking contention, disk pressure, slow query).

---

## Request Topology (Key Paths)

```
User → svc10 → ts-gateway-service
                              │
              ┌───────────────┼────────────────┐
              ▼               ▼                ▼
        svc02  svc37  svc36
              │               │                │
        svc40  svc09  svc21
              │          svc34   svc26
        svc41    svc62  svc34
        svc47    svc35 svc60
                         svc57   svc39
                         svc61    svc04
                                           svc55
                                           svc18
                                           svc45
                                           svc28
                                           svc33
                                           svc53
```

Booking is the deepest transactional path: it touches authentication, travel, multiple payment paths, and several add-ons, and each stage in turn reads/writes its data-store pod.

---

## Metric Channel Reference

Each pod exposes a subset of the following metric channels in the historian, named `{pod}_{metric_type}`:

| Suffix | Description | Units | Typical coverage |
|---|---|---|---|
| `_cpu` | CPU usage | millicores (m) | every pod |
| `_mem` | Resident memory usage | MB | every application pod, every database pod |
| `_workload` | Request rate / throughput | RPS | application services that receive HTTP traffic |
| `_latency-50` | P50 request latency | seconds | HTTP-facing application services |
| `_latency-90` | P90 request latency | seconds | HTTP-facing application services |

Coverage notes:
- **HTTP-facing application services** typically expose all five channels (`_cpu`, `_mem`, `_workload`, `_latency-50`, `_latency-90`).
- **Back-office and admin services** that don't serve user-facing traffic generally expose only `_cpu` / `_mem` (sometimes also `_workload`). Examples: `svc52`, `svc19`, `svc32`, `svc31`, `svc49`, `svc13`, `svc51`, `svc50`, `svc30`, `svc48`, `svc44`, `svc27`.
- **Data-store pods** (`ts-*-mongo`, `svc06`) expose only `_cpu` / `_mem`. They don't serve HTTP traffic, so workload and latency aren't directly instrumented.

**Example channel names:** `ts-travel-service_cpu`, `ts-order-service_latency-90`, `ts-gateway-service_workload`, `ts-travel-mongo_mem`, `ts-voucher-mysql_cpu`.
