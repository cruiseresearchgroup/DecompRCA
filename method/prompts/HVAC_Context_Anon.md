# Building HVAC System — Operational System Documentation

**Facility:** A two-floor commercial building served by a packaged air-handling unit with zone terminal boxes.
**Document scope:** Process architecture, refrigeration cycle, instrumentation, and historian channel inventory of the AHU and associated terminal distribution.

---

## System Overview

A air-handling unit conditions outdoor and return air (heating and/or cooling) and delivers it indoors via ductwork. The unit operates autonomously under building-management-system (BMS) supervision; sensor readings, actuator commands, and operating-state indicators are recorded continuously by the historian.

**Airflow path:** outdoor air enters through the OA damper while return air re-enters through the RA damper; the two streams blend in the mixed-air plenum, are drawn across the indoor coil (evaporator) by the supply fan, and the conditioned supply air is delivered to occupied zones. Downstream Variable Air Volume (VAV) terminal boxes modulate airflow per zone and provide electric reheat.

**Refrigeration cycle:** the compressor pressurises refrigerant vapour from the evaporator and pumps it to the outdoor coil (condenser), where heat is rejected to outdoor air via the outdoor fan. The high-pressure liquid throttles through a thermal expansion valve and re-enters the evaporator to absorb heat from the supply-air stream. Compressors may be staged (Stage 1 ≈ 67 % capacity, Stage 2 = 100 % capacity) to modulate cooling output.

Different unit configurations are documented:
- A laboratory unit (Trane YCD150, 12.5 ton, EER 9.6) serving 10 VAV zones with electric resistance reheat in a two-storey office emulator.
- Field-deployed commercial AHU (a 7.5-ton restaurant unit and a 10-ton distribution-center unit).
- A single-zone configuration (5,500 sq-ft office, ASHRAE Climate Zone 3C) with a two-stage scroll compressor on R410A refrigerant.

---

## Subsystems & Signal Reference

### 1. Air Handling and Distribution

The OA and RA dampers control the fraction of outdoor vs return air mixed into the supply stream; their positions are synchronised so that OA + RA = 1. The mixed air is conditioned by the evaporator and pushed through the duct system by the supply fan.

| Label | Type | Description |
|---|---|---|
| `AHU_OUTDOORAIR_DAMPER_POS` | actuator | OA damper control signal (0 = fully closed, 1 = fully open). |
| `AHU_RETURNAIR_DAMPER_POS` | actuator | RA damper control signal; complement of OA damper. |
| `AHU_OUTDOORAIR_TEMP` | sensor | Outdoor air temperature (°F or °C). Weather, not actuated. |
| `AHU_MIXEDAIR_TEMP` | sensor | Mixed air temperature; blend of OA and RA before the evaporator. |
| `AHU_SUPPLYAIR_TEMP` | sensor | Supply air temperature; conditioned air leaving the AHU. |
| `AHU_RETURNAIR_TEMP` | sensor | Return air temperature; air returning from the zones. |
| `AHU_SUPPLYAIR_FLOW` | sensor | Supply air volumetric flow rate (ACFM or cfm). |
| `AHU_RETURNAIR_FLOW` | sensor | Return air volumetric flow rate (cfm). |
| `AHU_OUTDOORAIR_FLOW` | sensor | Outdoor air volumetric flow rate (cfm). |
| `AHU_SUPPLYAIR_HUMIDITY` / `AHU_RETURNAIR_HUMIDITY` / `AHU_OUTDOORAIR_HUMIDITY` / `AHU_MIXEDAIR_HUMIDITY` | sensor | Relative humidity at each duct location. |
| `AHU_SUPPLYFAN_POWER` | sensor | Supply fan electricity consumption (W). |

### 2. Refrigeration Cycle

Refrigerant flows compressor → condenser (outdoor coil) → expansion valve → evaporator (indoor coil) and back to the compressor. Compressor staging modulates cooling capacity.

| Label | Type | Description |
|---|---|---|
| `AHU_COMPRESSOR_POWER_1` | sensor | Compressor 1 electricity consumption (W). |
| `AHU_COMPRESSOR_POWER_2` | sensor | Compressor 2 electricity consumption (W). |
| `AHU_COMPRESSOR_POWER` | sensor | Single-compressor power (Stage 1) where one compressor is installed. |
| `AHU_COMPRESSOR_STAGE_STATE` | state | Compressor stage status (0 = off, 0.67 = Stage 1, 1 = Stage 2). |
| `AHU_REFG_DISC_PRES` / `AHU_REFG_DISC_PRES_1/2` | sensor | Refrigerant discharge pressure. |
| `AHU_REFG_SUCT_PRES` / `AHU_REFG_SUCT_PRES_1/2` | sensor | Refrigerant suction pressure. |
| `AHU_REFG_COND_PRES` | sensor | Refrigerant condenser-outlet pressure. |
| `AHU_REFG_DISC_TEMP` / `AHU_REFG_DISC_TEMP_1/2` | sensor | Refrigerant discharge line temperature. |
| `AHU_REFG_SUCT_TEMP` / `AHU_REFG_SUCT_TEMP_1/2` | sensor | Refrigerant suction line temperature. |
| `AHU_REFG_COND_TEMP` / `AHU_REFG_COND_TEMP_1/2` | sensor | Refrigerant condenser-outlet temperature. |
| `AHU_LA_COND_TEMP` | sensor | Air temperature leaving the condenser. |
| `AHU_SEN_CAPA` | sensor | Sensible cooling capacity (W). |
| `AHU_TOT_CAPA` | sensor | Total cooling capacity (W). |

### 3. Energy and Operating State

Aggregate electrical/gas consumption and occupancy mode for the AHU and broader HVAC system.

| Label | Type | Description |
|---|---|---|
| `AHU_TOTAL_POWER` | sensor | AHU total electricity consumption (W). |
| `PLANT_TOTAL_POWER` | sensor | Total HVAC electricity including VAV reheat (W). |
| `AHU_GAS_CUMULATIVE` | sensor | Natural gas consumption (SCFM). |
| `OCCU_MOD` | state | Occupancy mode indicator (1 = occupied, 0 = unoccupied). |

### 4. Zones and Terminal Distribution

Each zone is served by a VAV box that throttles airflow and provides electric reheat. Zone temperature/humidity sensors measure the actual delivered conditions.

| Label | Type | Description |
|---|---|---|
| `ZONE_HEATING_SETPOINT` | setpoint | Heating temperature setpoint (shared across rooms). |
| `ZONE_COOLING_SETPOINT` | setpoint | Cooling temperature setpoint (shared across rooms). |
| `ZONE_ROOMTEMP_F1R05` … `ZONE_ROOMTEMP_F2R02` | sensor | Per-room ambient temperature. |
| `ZONE_ROOMHUMIDITY_F1R05` … `ZONE_ROOMHUMIDITY_F2R02` | sensor | Per-room ambient relative humidity. |
| `ZONEBOX_ROOMSUPPLYTEMP_F1R05` … `ZONEBOX_ROOMSUPPLYTEMP_F2R02` | sensor | Per-VAV-box supply air temperature. |
| `ZONEBOX_ROOMPOWER_F1R05` … `ZONEBOX_ROOMPOWER_F2R02` | sensor | Per-VAV-box reheat power consumption. |
| `ZA_TEMP` | sensor | Zone air temperature (single-zone configuration). |
| `ZA_HUM` | sensor | Zone air relative humidity (single-zone configuration). |
| `ZA_TEMP_SPT` | setpoint | Zone air temperature setpoint (single-zone configuration). |
