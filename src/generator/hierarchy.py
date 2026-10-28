"""Builds master records parent-first: plants -> lines -> machines -> sensors. No randomness needed."""
from datetime import date, timedelta
from decimal import Decimal

from src.config import GeneratorConfig
from src.generator import ids

# Plausible physical settings per sensor type. Documented assumptions, all configurable here.
SENSOR_SPECS = {
    "TEMP": dict(unit="degC", min=-20.0, max=200.0, run=70.0, idle=40.0, noise=1.5),
    "VIB": dict(unit="mm/s", min=0.0, max=50.0, run=2.5, idle=0.4, noise=0.25),
}
SENSOR_TYPES = list(SENSOR_SPECS)
MACHINE_TYPES = ["CNC_MILL", "PUMP", "COMPRESSOR", "CONVEYOR"]
TIMEZONES = ["UTC", "UTC", "UTC"]  # synthetic; kept simple


def build_hierarchy(cfg: GeneratorConfig) -> dict[str, list[dict]]:
    plants, lines, machines, sensors = [], [], [], []

    for p in range(1, cfg.n_plants + 1):
        plants.append(dict(
            plant_id=ids.plant_id(p), plant_name=f"Plant {p:03d}",
            timezone=TIMEZONES[(p - 1) % len(TIMEZONES)], status="ACTIVE",
            commissioned_on=date(2015, 1, 1) + timedelta(days=30 * p)))

    line_counter: dict[str, int] = {}
    for i in range(cfg.n_lines):  # spread lines round-robin over plants
        plant = plants[i % cfg.n_plants]["plant_id"]
        line_counter[plant] = line_counter.get(plant, 0) + 1
        lid = ids.line_id(plant, line_counter[plant])
        lines.append(dict(line_id=lid, plant_id=plant,
                          line_name=f"Line {line_counter[plant]:03d}", status="ACTIVE"))

    machine_counter: dict[str, int] = {}
    for i in range(cfg.n_machines):  # spread machines round-robin over lines
        lid = lines[i % cfg.n_lines]["line_id"]
        machine_counter[lid] = machine_counter.get(lid, 0) + 1
        k = machine_counter[lid]
        mid = ids.machine_id(lid, k)
        machines.append(dict(
            machine_id=mid, line_id=lid, machine_name=f"Machine {k:03d}",
            machine_type=MACHINE_TYPES[i % len(MACHINE_TYPES)], status="OPERATIONAL",
            installed_on=date(2018, 1, 1) + timedelta(days=7 * i)))

    for m in machines:
        for k in range(cfg.sensors_per_machine):  # TEMP-01, VIB-01, TEMP-02, VIB-02 ...
            code = SENSOR_TYPES[k % len(SENSOR_TYPES)]
            seq = k // len(SENSOR_TYPES) + 1
            spec = SENSOR_SPECS[code]
            sensors.append(dict(
                sensor_id=ids.sensor_id(m["machine_id"], code, seq), machine_id=m["machine_id"],
                sensor_type=code, sensor_seq=seq, unit=spec["unit"],
                min_plausible=Decimal(str(spec["min"])), max_plausible=Decimal(str(spec["max"])),
                sampling_interval_s=cfg.sampling_interval_s, status="ACTIVE"))

    return dict(plants=plants, lines=lines, machines=machines, sensors=sensors)
