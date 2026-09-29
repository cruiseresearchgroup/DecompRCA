# Microservice Platform — Operational System Documentation

**Asset:** A cloud-native microservice platform.
**Document scope:** Service inventory, request topology, and observability metrics for the platform.

---

## System Overview

The platform is an e-commerce system deployed on Kubernetes. End users browse the product svc13, add items to a shopping cart, and complete purchases through an online checkout flow. The system is composed of 11 services written in multiple languages (Go, Java, C#, Node.js, Python, Redis); each service is independently deployed and instrumented.

All services emit standard observability metrics — CPU usage, memory usage, and request latency — to a metrics historian. The historian publishes per-service columns following the convention `{service}_{metric_type}`, where metric types include `_cpu` (millicores), `_mem` (MB), and `_latency` / `_latency-90` (seconds, P90).

---

## Service Inventory

| Service | Language | Role | Calls |
|---|---|---|---|
| `svc20` | Go | Renders the web UI; orchestrates all backend services | all backend services |
| `svc06` | C# | Manages shopping svc14; uses Redis | svc17-cart |
| `svc01` | Go | Lists and searches products (in-memory) | none |
| `svc03` | Node.js | Converts prices between currencies | none |
| `svc09` | Node.js | Processes (mock) credit-card payments | none |
| `svc16` | Go | Provides shipping cost estimates | none |
| `svc11` | Python | Sends order confirmation emails (mock) | none |
| `svc05` | Go | Orchestrates the full checkout flow | cart, product, currency, payment, shipping, email |
| `svc10` | Python | Suggests related products | svc01 |
| `svc04` | Java | Serves context-based advertisements | none |
| `svc17-cart` | Redis | In-memory store for cart contents | none |

---

## Request Topology

```
User → svc20
         ├── svc01   (browse / search)
         ├── svc10 → svc01
         ├── svc03         (price conversion)
         ├── svc04               (ads)
         ├── svc06 → svc17-cart
         └── svc05
               ├── svc06 → svc17-cart
               ├── svc01
               ├── svc03
               ├── svc09
               ├── svc16
               └── svc11
```

---

## Metric Channel Reference

Each service exposes the following metric channels in the historian, named `{service}_{metric_type}`:

| Suffix | Description | Units |
|---|---|---|
| `_cpu` | CPU usage | millicores (m) |
| `_mem` | Resident memory usage | MB |
| `_latency` / `_latency-90` | P90 request latency | seconds |

**Example channel names:** `frontend_cpu`, `cartservice_latency`, `svc17-cart_mem`, `checkoutservice_cpu`.
