# Water Treatment System — Operational System Documentation

**Facility:** A six-stage water-treatment plant.
**Document scope:** Process architecture, instrumentation, control topology, and historian channel inventory of the plant.

---

## Facility Information

The facility is a six-stage water-treatment testbed that produces filtered, dechlorinated, and reverse-osmosis-purified water from a raw-water source. End-to-end throughput passes sequentially through Stage 1 (raw-water storage), Stage 2 (chemical dosing), Stage 3 (ultrafiltration, UF), Stage 4 (dechlorination by UV), Stage 5 (reverse osmosis, RO), and Stage 6 (backwash). RO permeate exits the plant; reject and backwash water are recirculated.

All process variables and actuator states are recorded continuously by the plant historian at 1-second resolution. The historian carries 51 channels covering level transmitters, flow transmitters, analyser transmitters, pressure transmitters, motorised valves, pumps, and a UV lamp. Channel names follow the pattern `<type><stage><loop>`, where `type` encodes the instrument function (`LIT` level, `FIT` flow, `AIT` analyser, `PIT` pressure, `DPIT` differential pressure, `MV` motorised valve, `P` pump, `UV` UV lamp), `stage` is the process stage `1`–`6`, and `loop` is a two-digit loop number (e.g., `S1_LEVEL_01` is the level transmitter in stage 1, loop 01).

---

## System Overview

**Process workflow:** raw water enters Stage 1 and is buffered in a raw-water tank. Stage 2 doses chemicals (sodium hypochlorite, hydrochloric acid) under closed-loop pH and ORP control. Stage 3 passes the conditioned water through ultrafiltration membranes; differential pressure across the membranes is monitored to detect fouling and trigger backwash. Stage 4 exposes the UF permeate to a UV lamp to dechlorinate residual hypochlorite. Stage 5 forces the dechlorinated water through RO membranes at high pressure; permeate is the product, reject is recirculated. Stage 6 manages the periodic backwash of the UF and RO membranes.

The plant runs in continuous, unattended operation. Each stage is governed by a dedicated PLC executing process logic against tank-level setpoints, flow setpoints, and quality thresholds. A SCADA workstation provides supervisory monitoring with manual-override capability for any actuator.

---

## Subsystems & Signal Reference

### 1. Stage 1 — Raw Water Supply and Storage

Raw water enters the plant from a public supply line and is buffered in a raw-water tank. Stage 1 PLC opens the inlet motorised valve to fill the tank when the level transmitter falls below a low setpoint, and closes it when the level reaches a high setpoint. Two transfer pumps lift water from the raw-water tank to Stage 2.

| Label | Type | Description |
|---|---|---|
| `S1_LEVEL_01` | sensor (level) | Raw-water tank level (mm). |
| `S1_FLOW_01` | sensor (flow) | Inlet flow rate to the raw-water tank (m³/h). |
| `S1_VALVE_01` | actuator | Motorised inlet valve to the raw-water tank (open/closed). |
| `S1_PUMP_01` | actuator | Raw-water transfer pump 1 (running/stopped). |
| `S1_PUMP_02` | actuator | Raw-water transfer pump 2 — standby (running/stopped). |

### 2. Stage 2 — Pre-Treatment (Chemical Dosing)

Stage 2 conditions the raw water by dosing sodium hypochlorite (chlorination) and hydrochloric acid (pH control). Three analyser transmitters monitor pH (`S2_QUALITY_03`), conductivity (`S2_QUALITY_01`), and oxidation–reduction potential (`S2_QUALITY_02`) of the conditioned water. Six dosing pumps (`S2_PUMP_03`–`S2_PUMP_01`) inject the chemicals in closed-loop control against the analyser readings.

| Label | Type | Description |
|---|---|---|
| `S2_FLOW_01` | sensor (flow) | Outflow rate from Stage 2 to Stage 3 (m³/h). |
| `S2_QUALITY_01` | sensor (quality) | Conductivity analyser (μS/cm). |
| `S2_QUALITY_03` | sensor (quality) | pH analyser. |
| `S2_QUALITY_02` | sensor (quality) | ORP analyser (mV). |
| `S2_VALVE_01` | actuator | Motorised valve into Stage 2 (open/closed). |
| `S2_PUMP_03` … `S2_PUMP_01` | actuator | Chemical dosing pumps (running/stopped). |

### 3. Stage 3 — Ultrafiltration (UF)

The UF stage removes suspended solids by forcing water through a hollow-fibre membrane. A differential pressure indicator (`S3_DIFFPRESS_01`) measures the pressure drop across the membrane; when it exceeds a threshold the PLC triggers a backwash sequence. Two pumps (`S3_PUMP_02`, `S3_PUMP_01`) feed the UF unit and four motorised valves (`S3_VALVE_03`–`S3_VALVE_04`) route water either through the UF membrane (forward flow) or through a backwash path.

| Label | Type | Description |
|---|---|---|
| `S3_LEVEL_01` | sensor (level) | UF feed-tank level (mm). |
| `S3_FLOW_01` | sensor (flow) | UF feed flow rate (m³/h). |
| `S3_DIFFPRESS_01` | sensor (Δ pressure) | Differential pressure across the UF membrane (kPa). High value = membrane fouling. |
| `S3_VALVE_03` … `S3_VALVE_04` | actuator | Motorised valves on UF/backwash routing (open/closed). |
| `S3_PUMP_02` | actuator | UF feed pump (running/stopped). |
| `S3_PUMP_01` | actuator | UF transfer pump (running/stopped). |

### 4. Stage 4 — Dechlorination (UV)

The UV stage removes residual free chlorine from the UF permeate before the water enters the RO membranes (chlorine damages the RO film). A UV lamp (`S4_UVLAMP_01`) is energised when feed flow is present; analyser transmitters monitor conductivity (`S4_QUALITY_01`) and ORP (`S4_QUALITY_02`) of the dechlorinated water.

| Label | Type | Description |
|---|---|---|
| `S4_LEVEL_01` | sensor (level) | UF permeate / RO feed-tank level (mm). |
| `S4_FLOW_01` | sensor (flow) | UF permeate flow rate to UV (m³/h). |
| `S4_QUALITY_01` | sensor (quality) | Hardness / conductivity analyser. |
| `S4_QUALITY_02` | sensor (quality) | ORP analyser of dechlorinated water (mV). |
| `S4_UVLAMP_01` | actuator | UV lamp on/off. |
| `S4_PUMP_03` … `S4_PUMP_04` | actuator | Stage-4 transfer pumps (running/stopped). |

### 5. Stage 5 — Reverse Osmosis (RO)

The RO stage forces dechlorinated water through a semi-permeable membrane at high pressure to produce purified product water. Pressure transmitters (`S5_PRESSURE_02`–`S5_PRESSURE_03`) monitor inlet, membrane, and outlet pressures; analyser transmitters (`S5_QUALITY_02`–`S5_QUALITY_04`) report quality of feed, permeate, reject, and product streams. Flow transmitters (`S5_FLOW_03`–`S5_FLOW_01`) measure feed, permeate, reject, and recirculation flows. Two high-pressure pumps (`S5_PUMP_02`, `S5_PUMP_01`) drive the RO membrane.

| Label | Type | Description |
|---|---|---|
| `S5_PRESSURE_02` | sensor (pressure) | RO inlet pressure (kPa). |
| `S5_PRESSURE_01` | sensor (pressure) | RO membrane pressure (kPa). |
| `S5_PRESSURE_03` | sensor (pressure) | RO outlet / reject pressure (kPa). |
| `S5_FLOW_03` | sensor (flow) | RO feed flow (m³/h). |
| `S5_FLOW_04` | sensor (flow) | RO permeate flow (m³/h). |
| `S5_FLOW_02` | sensor (flow) | RO reject flow (m³/h). |
| `S5_FLOW_01` | sensor (flow) | RO recirculation flow (m³/h). |
| `S5_QUALITY_02` | sensor (quality) | RO feed water quality. |
| `S5_QUALITY_01` | sensor (quality) | RO permeate water quality (low conductivity = pure). |
| `S5_QUALITY_03` | sensor (quality) | RO reject water quality. |
| `S5_QUALITY_04` | sensor (quality) | RO product water quality. |
| `S5_PUMP_02` | actuator | RO high-pressure pump 1 (running/stopped). |
| `S5_PUMP_01` | actuator | RO high-pressure pump 2 (running/stopped). |

### 6. Stage 6 — Backwash and Disposal

Stage 6 manages periodic backwash of the UF and RO membranes. A flow transmitter (`S6_FLOW_01`) measures backwash flow; three pumps (`S6_PUMP_03`–`S6_PUMP_02`) execute the backwash and drain sequences when scheduled or when triggered by membrane fouling indicators in earlier stages.

| Label | Type | Description |
|---|---|---|
| `S6_FLOW_01` | sensor (flow) | Backwash flow rate (m³/h). |
| `S6_PUMP_03` | actuator | Backwash pump 1 (running/stopped). |
| `S6_PUMP_01` | actuator | Backwash pump 2 (running/stopped). |
| `S6_PUMP_02` | actuator | Drain pump (running/stopped). |
