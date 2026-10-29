"""Phase 3B: failure scenarios, sensor faults, benign surges and preventive maintenance.

TWO steps, kept separate on purpose:
  1. plan_scenarios()      decides WHAT happens WHEN (pure planning, uses its own random stream).
  2. apply_scenarios()     rewrites the healthy baseline telemetry of one sensor to match the plan.

The healthy baseline (telemetry.py) is never modified, so a config with every scenario switch at 0
reproduces the original starter data exactly (same md5 checksum).

Random streams (all derived from cfg.seed, so everything is reproducible):
  [seed, sensor_index]      healthy baseline (unchanged since Phase 2)
  [seed, 9001]              the scenario plan
  [seed, sensor_index, 7]   scenario effects on one sensor
Ground truth (failure onset/time) lives in the plan and in failure_event. It is used ONLY to shape the
synthetic signal and to write records. The risk engine must never read it.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from src.config import GeneratorConfig

CATEGORIES = ("BEARING_WEAR", "OVERHEATING", "LUBRICATION", "MISALIGNMENT", "ELECTRICAL")
FAULT_TYPES = ("DRIFT", "FLATLINE", "DROPOUT")

# How many days before the failure the first symptoms appear (min, max).
LEAD_DAYS = {"BEARING_WEAR": (5, 9), "OVERHEATING": (3, 6), "LUBRICATION": (4, 8),
             "MISALIGNMENT": (4, 7), "ELECTRICAL": (2, 5)}
SEVERITY_CHOICES = {"BEARING_WEAR": ("MAJOR", "CRITICAL"), "OVERHEATING": ("MAJOR", "CRITICAL"),
                    "LUBRICATION": ("MINOR", "MAJOR"), "MISALIGNMENT": ("MINOR", "MAJOR"),
                    "ELECTRICAL": ("MAJOR", "CRITICAL")}
REPAIR_HOURS = {"MINOR": (2, 5), "MAJOR": (5, 12), "CRITICAL": (10, 24)}
FAULT_HOURS = {"DRIFT": (72, 120), "FLATLINE": (8, 24), "DROPOUT": (4, 14)}
BASELINE_DAYS_BEFORE_ONSET = 3   # every failing machine has at least this many healthy days first
QUIET_DAYS_AT_END = 4            # failure + repair always finish before the data ends


def _sec(dt: datetime) -> datetime:
    return dt.replace(microsecond=0)


def _after(dt: datetime, hours: float) -> datetime:
    return _sec(dt + timedelta(seconds=round(hours * 3600)))


@dataclass(frozen=True)
class FailureScenario:
    failure_id: str
    machine_id: str
    category: str
    severity: str
    gain: float                 # signal strength 0.3-1.0 (low = hard to detect)
    onset: datetime             # degradation starts (ground truth)
    failure_at: datetime
    detected_at: datetime
    wo_created: datetime
    wo_started: datetime
    wo_completed: datetime
    returned_to_service: datetime


@dataclass(frozen=True)
class SensorFault:
    sensor_id: str
    machine_id: str
    sensor_type: str
    fault_type: str             # DRIFT | FLATLINE | DROPOUT
    start: datetime
    end: datetime               # sensor restored
    flagged_at: datetime        # when the sensor is marked FAULTY (later than the real start)
    amplitude: float            # drift size (sensor units); unused for the other types


@dataclass(frozen=True)
class BenignEvent:
    machine_id: str
    start: datetime
    end: datetime
    temp_add: float
    vib_mult: float


@dataclass(frozen=True)
class PreventiveJob:
    machine_id: str
    created_at: datetime
    scheduled_for: datetime
    started_at: datetime
    completed_at: datetime


@dataclass(frozen=True)
class ScenarioPlan:
    failures: tuple = ()
    sensor_faults: tuple = ()
    benign: tuple = ()
    preventive: tuple = ()

    def failure_for(self, machine_id: str):
        return next((f for f in self.failures if f.machine_id == machine_id), None)

    def down_windows(self, machine_id: str) -> list[tuple[datetime, datetime]]:
        """Periods when the machine is stopped (failed or in maintenance): telemetry shows MAINTENANCE."""
        w = [(f.failure_at, f.returned_to_service) for f in self.failures if f.machine_id == machine_id]
        w += [(p.started_at, p.completed_at) for p in self.preventive if p.machine_id == machine_id]
        return sorted(w)


def plan_scenarios(cfg: GeneratorConfig, h: dict) -> ScenarioPlan:
    rng = np.random.default_rng(np.random.SeedSequence([cfg.seed, 9001]))
    machines = [m["machine_id"] for m in h["machines"]]
    sensors = h["sensors"]
    start, end = cfg.start, cfg.end
    if cfg.n_failures > len(machines):
        raise ValueError("n_failures cannot exceed n_machines (one failure per machine)")
    if cfg.n_sensor_faults > len(sensors):
        raise ValueError("n_sensor_faults cannot exceed the number of sensors")

    # ---------- failures ----------
    chosen = sorted(int(i) for i in rng.choice(len(machines), cfg.n_failures, replace=False))
    order = [int(i) for i in rng.permutation(len(CATEGORIES))]
    failures = []
    for k, mi in enumerate(chosen):
        machine = machines[mi]
        cat = CATEGORIES[order[k % len(CATEGORIES)]]
        lead_days = float(rng.uniform(*LEAD_DAYS[cat]))
        earliest = lead_days + BASELINE_DAYS_BEFORE_ONSET
        latest = cfg.days - QUIET_DAYS_AT_END
        if earliest >= latest:
            raise ValueError(f"days={cfg.days} is too short for a {cat} scenario (needs > {earliest + QUIET_DAYS_AT_END:.0f})")
        failure_at = start + timedelta(days=float(rng.uniform(earliest, latest)))
        failure_at = failure_at.replace(second=0, microsecond=0)
        onset = _sec(failure_at - timedelta(days=lead_days))
        severity = str(rng.choice(SEVERITY_CHOICES[cat]))
        # every third failure is deliberately subtle (weak signal) so the later evaluation is not too easy
        gain = float(rng.uniform(0.3, 0.5) if k % 3 == 2 else rng.uniform(0.7, 1.0))
        if rng.random() < 0.4:   # an operator notices the late symptoms before the machine stops
            detected = _sec(onset + (failure_at - onset) * float(rng.uniform(0.6, 0.95)))
        else:
            detected = failure_at
        created = _after(failure_at, float(rng.uniform(2, 20)) / 60)
        started = _after(created, float(rng.uniform(1, 4)))
        completed = _after(started, float(rng.uniform(*REPAIR_HOURS[severity])))
        failures.append(FailureScenario(
            failure_id=f"FAIL-{machine}-001", machine_id=machine, category=cat, severity=severity, gain=round(gain, 3),
            onset=onset, failure_at=failure_at, detected_at=detected, wo_created=created, wo_started=started,
            wo_completed=completed, returned_to_service=_after(completed, 0.5)))
    fail_by_machine = {f.machine_id: f for f in failures}

    # ---------- sensor faults (never overlapping the failure window of their own machine) ----------
    faults = []
    for j, si in enumerate(int(i) for i in rng.choice(len(sensors), cfg.n_sensor_faults, replace=False)):
        s = sensors[si]
        ftype = FAULT_TYPES[j % len(FAULT_TYPES)]
        f = fail_by_machine.get(s["machine_id"])
        for _ in range(200):
            dur = float(rng.uniform(*FAULT_HOURS[ftype]))
            f_start = _sec(start + timedelta(days=float(rng.uniform(1, cfg.days - 6))))
            f_end = _after(f_start, dur)
            if f is None or f_end <= f.onset or f_start >= f.returned_to_service:
                break
        else:
            raise ValueError("could not place a sensor fault without overlapping a failure")
        flag = {"DRIFT": 0.6 * dur, "FLATLINE": 4.0, "DROPOUT": 1.0}[ftype]
        amp = float(rng.uniform(10, 18) if s["sensor_type"] == "TEMP" else rng.uniform(1.0, 2.0))
        faults.append(SensorFault(s["sensor_id"], s["machine_id"], s["sensor_type"], ftype, f_start, f_end,
                                  _after(f_start, flag), round(amp, 3)))

    # ---------- benign surges on healthy machines ----------
    healthy = [m for m in machines if m not in fail_by_machine]
    benign = []
    if cfg.n_benign_events:
        if not healthy:
            raise ValueError("n_benign_events needs at least one healthy machine")
        for _ in range(cfg.n_benign_events):
            m = healthy[int(rng.integers(len(healthy)))]
            b_start = _sec(start + timedelta(days=float(rng.uniform(1, cfg.days - 2))))
            b_end = _after(b_start, float(rng.uniform(3, 8)))
            benign.append(BenignEvent(m, b_start, b_end, round(float(rng.uniform(6, 10)), 2),
                                      round(float(rng.uniform(1.6, 2.2)), 2)))

    # ---------- preventive maintenance ----------
    preventive = []
    if cfg.pm_interval_days > 0:
        for mi, m in enumerate(machines):
            first_day = 3 + int(mi * cfg.pm_interval_days / len(machines))
            sched = start + timedelta(days=first_day, hours=10, minutes=15 * (mi % 4))
            while sched < end - timedelta(days=1):
                dur = float(rng.uniform(2, 4))
                p_started = _after(sched, float(rng.uniform(5, 20)) / 60)
                p_completed = _after(p_started, dur)
                f = fail_by_machine.get(m)
                if f is None or p_completed <= f.failure_at or p_started >= f.returned_to_service:
                    preventive.append(PreventiveJob(m, sched - timedelta(days=2), sched, p_started, p_completed))
                sched += timedelta(days=cfg.pm_interval_days)

    return ScenarioPlan(tuple(failures), tuple(faults), tuple(benign), tuple(preventive))


# ----------------------------------------------------------------------------------------------
# Signal effects
# ----------------------------------------------------------------------------------------------
def _hours(cfg: GeneratorConfig, dt: datetime) -> float:
    return (dt - cfg.start).total_seconds() / 3600.0


def _temp_effect(cat: str, p, g: float, rng, noise: float):
    n = len(p)
    spike = rng.random(n) < 0.25 * p ** 2
    spike_size = 12.0 * g * rng.uniform(0.5, 1.5, n)
    burst = rng.normal(0.0, noise, n)
    if cat == "BEARING_WEAR":
        return 10.0 * g * p ** 1.5
    if cat == "OVERHEATING":
        return 40.0 * g * p ** 1.3
    if cat == "LUBRICATION":
        return 14.0 * g * p + burst * p * g
    if cat == "MISALIGNMENT":
        return 6.0 * g * p
    return 8.0 * g * p + np.where(spike, spike_size, 0.0)          # ELECTRICAL


def _vib_effect(cat: str, p, g: float, t, run: float, rng, noise: float):
    n = len(p)
    spike = rng.random(n) < 0.2 * p ** 2
    spike_size = run * 1.5 * g * rng.uniform(0.5, 1.5, n)
    burst = rng.normal(0.0, noise, n)
    if cat == "BEARING_WEAR":
        return run * 2.4 * g * p ** 2
    if cat == "OVERHEATING":
        return 0.15 * run * g * p
    if cat == "LUBRICATION":
        return run * 1.0 * g * p ** 1.2 + 1.5 * burst * g * p
    if cat == "MISALIGNMENT":
        return run * 1.4 * g * np.sqrt(p) + 0.5 * run * g * p * np.sin(2 * np.pi * t / 6.0) + burst * g * p
    return np.where(spike, spike_size, 0.0) + 0.5 * burst * g * p   # ELECTRICAL


def apply_scenarios(cfg: GeneratorConfig, sensor: dict, sensor_index: int, df: pd.DataFrame,
                    plan: ScenarioPlan, spec: dict) -> pd.DataFrame:
    """Return a copy of the healthy frame `df` with this sensor's scenario effects applied."""
    t = (df["event_ts"] - cfg.start).dt.total_seconds().to_numpy() / 3600.0
    n = len(t)
    rng = np.random.default_rng(np.random.SeedSequence([cfg.seed, sensor_index, 7]))
    val = df["reading_value"].to_numpy(dtype=float).copy()
    state = df["machine_state"].to_numpy(dtype=object).copy()
    running = state == "RUNNING"
    activity = np.where(running, 1.0, 0.4)
    machine, stype = sensor["machine_id"], sensor["sensor_type"]
    sensor_gain = float(rng.uniform(0.8, 1.1))   # drawn always, so streams stay aligned

    # 1) degradation before a failure
    f = plan.failure_for(machine)
    if f is not None:
        t0, t1 = _hours(cfg, f.onset), _hours(cfg, f.failure_at)
        p = np.clip((t - t0) / (t1 - t0), 0.0, 1.0) * (t < t1)
        g = f.gain * sensor_gain
        if stype == "TEMP":
            eff = _temp_effect(f.category, p, g, rng, spec["noise"])
        else:
            eff = _vib_effect(f.category, p, g, t, spec["run"], rng, spec["noise"])
        val += eff * activity

    # 2) harmless surges on healthy machines
    for b in (b for b in plan.benign if b.machine_id == machine):
        s, e = _hours(cfg, b.start), _hours(cfg, b.end)
        ramp = np.clip(np.minimum(t - s, e - t) / 1.0, 0.0, 1.0) * running
        if stype == "TEMP":
            val += b.temp_add * ramp
        else:
            val *= 1.0 + (b.vib_mult - 1.0) * ramp

    # 3) machine stopped (failed or in maintenance): idle-level readings, state MAINTENANCE
    stopped = np.zeros(n, dtype=bool)
    for s, e in plan.down_windows(machine):
        stopped |= (t >= _hours(cfg, s)) & (t < _hours(cfg, e))
    idle_vals = spec["idle"] + rng.normal(0.0, spec["noise"], n)
    val = np.where(stopped, idle_vals, val)
    state = np.where(stopped, "MAINTENANCE", state)

    # 4) sensor faults act on the sensor itself, whatever the machine is doing
    for sf in (x for x in plan.sensor_faults if x.sensor_id == sensor["sensor_id"]):
        s, e = _hours(cfg, sf.start), _hours(cfg, sf.end)
        mask = (t >= s) & (t < e)
        if not mask.any():
            continue
        if sf.fault_type == "DRIFT":
            val = val + sf.amplitude * np.clip((t - s) / (e - s), 0.0, 1.0) * mask
        elif sf.fault_type == "FLATLINE":
            val = np.where(mask, val[np.argmax(mask)], val)
        else:  # DROPOUT: the reading is missing (stored as NULL)
            val = np.where(mask, np.nan, val)

    val = np.round(np.clip(val, float(sensor["min_plausible"]), float(sensor["max_plausible"])), 3)
    out = df.copy()
    out["reading_value"] = val
    out["machine_state"] = state
    return out


def plan_manifest(cfg: GeneratorConfig, plan: ScenarioPlan) -> dict:
    """Ground-truth description of everything injected. Written next to the data for evaluation and audits."""
    iso = lambda d: d.isoformat()  # noqa: E731
    return {
        "seed": cfg.seed,
        "failures": [dict(failure_id=f.failure_id, machine_id=f.machine_id, category=f.category,
                          severity=f.severity, gain=f.gain, onset=iso(f.onset), failure_at=iso(f.failure_at),
                          returned_to_service=iso(f.returned_to_service)) for f in plan.failures],
        "sensor_faults": [dict(sensor_id=x.sensor_id, machine_id=x.machine_id, fault_type=x.fault_type,
                               start=iso(x.start), end=iso(x.end), flagged_at=iso(x.flagged_at),
                               amplitude=x.amplitude) for x in plan.sensor_faults],
        "benign_events": [dict(machine_id=b.machine_id, start=iso(b.start), end=iso(b.end),
                               temp_add=b.temp_add, vib_mult=b.vib_mult) for b in plan.benign],
        "preventive_jobs": [dict(machine_id=p.machine_id, started_at=iso(p.started_at),
                                 completed_at=iso(p.completed_at)) for p in plan.preventive],
    }
