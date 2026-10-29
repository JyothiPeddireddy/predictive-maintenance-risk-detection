"""Rule-based machine risk score (0-100). Explainable on purpose: no machine learning.

For each machine at a scoring time t the engine looks ONLY at data up to t:
  1. Sensor quality: a sensor is ignored when it is flagged FAULTY, is dropping out (many missing readings)
     or is flat-lined (identical readings). A sensor that disagrees strongly with its sibling is ignored too.
  2. Own baseline: the machine's normal level per sensor = median/MAD of RUNNING readings between 21 days and
     3 days ago. Readings taken while the machine was in MAINTENANCE are ignored.
  3. Three signals per sensor (all measured in "baseline spreads"):
       level  - how far the last-24h median is above the baseline            (sustained rise)
       trend  - how fast the last-72h readings are rising                     (growing problem)
       spikes - share of last-24h readings far above baseline, if spread out  (intermittent bursts;
                bursts that last under ~8 h are treated as harmless surges)
  4. Sensor score = strongest signal; type score = blend of the mean and the LOWEST valid sensor of that type (sensors must
     agree; a single unchecked sensor is trusted a bit less); machine score = best type + a small bonus if a second type is also elevated.
  5. After a corrective repair the old readings are dropped, so a repaired machine is not judged by its past.

Target leakage: this module reads no failure table and no failure column (a test checks the source text and the
input columns), and every rule is point-in-time (a test proves data after t is never used).
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.risk.data import RiskInputs, to_seconds, validate_inputs

H = 3600.0


@dataclass(frozen=True)
class RiskParams:
    baseline_days: float = 21.0
    baseline_gap_h: float = 72.0          # most recent 72 h are NOT part of the baseline
    min_baseline_valid_h: float = 36.0    # hours of RUNNING data needed for a baseline
    recent_h: float = 24.0
    min_recent_valid_h: float = 6.0
    trend_h: float = 72.0
    min_trend_valid_h: float = 18.0
    quality_h: float = 6.0
    dropout_frac: float = 0.3
    flatline_min_h: float = 4.0
    scale_floor_frac: float = 0.04        # baseline spread is never smaller than 4% of the baseline level
    z_low: float = 2.0                    # level score 0 at z_low, 100 at z_high
    z_high: float = 6.0
    trend_low: float = 0.5                # trend (spreads per day) scoring range
    trend_high: float = 2.0
    spike_k: float = 4.0
    spike_frac_high: float = 0.15
    spike_span_low_h: float = 8.0         # spikes spread over < 8 h = harmless surge
    spike_span_high_h: float = 16.0
    sibling_min_z: float = 4.0
    sibling_ratio: float = 0.25
    single_sensor_factor: float = 0.85
    min_weight: float = 0.5               # with 2+ sensors of one type: 0 = plain mean, 1 = lowest sensor only
    corroboration_weight: float = 0.25
    corroboration_floor: float = 20.0
    # Chosen on the TUNING seeds only, by one rule: the highest threshold that still catches >= 90% of failures
    # (see docs/risk_and_evaluation.md). The holdout seeds were not used.
    medium_threshold: float = 15.0
    warn_threshold: float = 30.0          # score >= this raises a warning


@dataclass
class SensorResult:
    sensor_id: str
    sensor_type: str
    usable: bool
    flags: list = field(default_factory=list)
    z_level: float = 0.0
    z_trend: float = 0.0
    spike_frac: float = 0.0
    score: float = 0.0
    notes: list = field(default_factory=list)


@dataclass
class MachineRisk:
    machine_id: str
    at: pd.Timestamp
    score: float
    band: str
    status: str
    n_usable_sensors: int
    n_sensors: int
    flags: list
    reasons: list


class _Series:
    """One sensor's readings as plain arrays (fast window slicing with searchsorted)."""
    __slots__ = ("sensor_id", "machine_id", "stype", "dt", "t", "v", "ok", "st_t", "st_faulty")

    def __init__(self, sensor_id, machine_id, stype, dt, t, v, running, st_t, st_faulty):
        self.sensor_id, self.machine_id, self.stype, self.dt = sensor_id, machine_id, stype, float(dt)
        self.t, self.v = t, v
        self.ok = running & ~np.isnan(v)
        self.st_t, self.st_faulty = st_t, st_faulty


class RiskEngine:
    def __init__(self, inputs: RiskInputs, params: RiskParams | None = None):
        self.p = params or RiskParams()
        validate_inputs(inputs)
        tel = inputs.telemetry.copy()
        tel["_t"] = to_seconds(tel["event_ts"])
        status = inputs.sensor_status.copy()
        status["_t"] = to_seconds(status["changed_at"])
        self.series: dict[str, list[_Series]] = {}
        tel_groups = {k: g.sort_values("_t") for k, g in tel.groupby("sensor_id")}
        st_groups = {k: g.sort_values("_t") for k, g in status.groupby("sensor_id")}
        for row in inputs.sensors.itertuples(index=False):
            g = tel_groups.get(row.sensor_id)
            if g is None:
                continue
            s = st_groups.get(row.sensor_id)
            st_t = s["_t"].to_numpy() if s is not None else np.array([])
            st_f = (s["new_status"] == "FAULTY").to_numpy() if s is not None else np.array([], dtype=bool)
            self.series.setdefault(row.machine_id, []).append(_Series(
                row.sensor_id, row.machine_id, row.sensor_type, row.sampling_interval_s, g["_t"].to_numpy(),
                g["reading_value"].to_numpy(dtype=float), (g["machine_state"] == "RUNNING").to_numpy(), st_t, st_f))
        self.machines = inputs.machines
        wo = inputs.work_orders
        fixed = wo[wo["maintenance_type"] == "CORRECTIVE"]
        self._repair_done = {m: np.sort(to_seconds(g["returned_to_service_at"]).clip(min=-1e18))
                             for m, g in fixed.groupby("machine_id")}
        for m, a in self._repair_done.items():
            self._repair_done[m] = a[~np.isnan(a)]

    # ------------------------------------------------------------------ per sensor
    def _reset_time(self, machine: str, t: float) -> float:
        """Time of the last finished corrective repair (older readings describe the machine before the repair)."""
        done = self._repair_done.get(machine)
        if done is None or len(done) == 0:
            return -np.inf
        i = np.searchsorted(done, t, side="right")
        return float(done[i - 1]) if i else -np.inf

    def _sensor(self, s: _Series, t: float, reset_t: float) -> SensorResult:
        p = self.p
        res = SensorResult(s.sensor_id, s.stype, usable=False)
        hi = int(np.searchsorted(s.t, t, side="right"))

        # ---- quality ----
        if len(s.st_t):
            j = int(np.searchsorted(s.st_t, t, side="right"))
            if j and s.st_faulty[j - 1]:
                res.flags.append("FLAGGED_FAULTY")
        q0 = int(np.searchsorted(s.t, t - p.quality_h * H, side="left"))
        qv = s.v[q0:hi]
        if len(qv) and np.isnan(qv).mean() >= p.dropout_frac:
            res.flags.append("DROPOUT")
        good = qv[~np.isnan(qv)]
        if len(good) * s.dt >= p.flatline_min_h * H and np.ptp(good) == 0:
            res.flags.append("FLATLINE")
        if res.flags:
            return res

        # ---- baseline (own history, 21 d ... 3 d ago, after the last repair) ----
        b_lo = int(np.searchsorted(s.t, max(t - p.baseline_days * 86400, reset_t), side="left"))
        b_hi = int(np.searchsorted(s.t, t - p.baseline_gap_h * H, side="right"))
        base = s.v[b_lo:b_hi][s.ok[b_lo:b_hi]] if b_hi > b_lo else np.array([])
        if len(base) * s.dt < p.min_baseline_valid_h * H:
            res.flags.append("NO_BASELINE")
            return res
        b_med = float(np.median(base))
        scale = max(1.4826 * float(np.median(np.abs(base - b_med))), p.scale_floor_frac * abs(b_med), 1e-6)

        # ---- recent window ----
        r_lo = int(np.searchsorted(s.t, max(t - p.recent_h * H, reset_t), side="left"))
        sel = s.ok[r_lo:hi]
        rv, rt = s.v[r_lo:hi][sel], s.t[r_lo:hi][sel]
        if len(rv) * s.dt < p.min_recent_valid_h * H:
            res.flags.append("INSUFFICIENT_RECENT")
            return res
        res.z_level = (float(np.median(rv)) - b_med) / scale

        # ---- trend (last 72 h) ----
        k_lo = int(np.searchsorted(s.t, max(t - p.trend_h * H, reset_t), side="left"))
        sel = s.ok[k_lo:hi]
        kv, kt = s.v[k_lo:hi][sel], s.t[k_lo:hi][sel]
        if len(kv) * s.dt >= p.min_trend_valid_h * H and kt[-1] - kt[0] >= 12 * H:
            slope_per_day = np.polyfit((kt - kt[0]) / 86400.0, kv, 1)[0]
            res.z_trend = float(slope_per_day / scale)

        # ---- spikes (must be spread over time to count) ----
        over = rt[rv > b_med + p.spike_k * scale]
        res.spike_frac = len(over) / len(rv)
        persist = 0.0
        if len(over) >= 3:
            span_h = (over[-1] - over[0]) / H
            persist = float(np.clip((span_h - p.spike_span_low_h) / (p.spike_span_high_h - p.spike_span_low_h), 0, 1))

        level = 100 * float(np.clip((res.z_level - p.z_low) / (p.z_high - p.z_low), 0, 1))
        trend = 100 * float(np.clip((res.z_trend - p.trend_low) / (p.trend_high - p.trend_low), 0, 1)) \
            if res.z_level > 1.0 else 0.0
        spike = 100 * float(np.clip(res.spike_frac / p.spike_frac_high, 0, 1)) * persist
        res.score = max(level, 0.9 * trend, 0.8 * spike)
        res.usable = True
        if level >= 30:
            res.notes.append(f"{s.sensor_id.split('-', 1)[-1][-8:]}: level {res.z_level:+.1f} spreads above baseline")
        if trend >= 30:
            res.notes.append(f"{s.sensor_id[-8:]}: rising {res.z_trend:.1f} spreads/day")
        if spike >= 30:
            res.notes.append(f"{s.sensor_id[-8:]}: {res.spike_frac:.0%} spikes over many hours")
        return res

    # ------------------------------------------------------------------ per machine
    def score_machine(self, machine: str, at) -> MachineRisk:
        p = self.p
        at = pd.Timestamp(at)
        at = at.tz_localize("UTC") if at.tzinfo is None else at.tz_convert("UTC")
        t = at.timestamp()
        reset_t = self._reset_time(machine, t)
        sensors = [self._sensor(s, t, reset_t) for s in self.series.get(machine, [])]
        flags, reasons = [], []
        for r in sensors:
            for f in r.flags:
                if f not in ("NO_BASELINE", "INSUFFICIENT_RECENT"):
                    flags.append(f"{r.sensor_id[-10:]}:{f}")

        type_scores = {}
        for kind in sorted({r.sensor_type for r in sensors}):
            valid = [r for r in sensors if r.sensor_type == kind and r.usable]
            if len(valid) >= 2:   # a sensor far above its healthy sibling is a sensor problem, not a machine problem
                top = max(valid, key=lambda r: r.z_level)
                rest = [r for r in valid if r is not top]
                if top.z_level >= p.sibling_min_z and max(r.z_level for r in rest) < p.sibling_ratio * top.z_level:
                    flags.append(f"{top.sensor_id[-10:]}:SENSOR_DISAGREEMENT")
                    valid = rest
            if not valid:
                continue
            sc = [r.score for r in valid]
            score = (1 - p.min_weight) * float(np.mean(sc)) + p.min_weight * float(min(sc))
            if len(valid) == 1:
                score *= p.single_sensor_factor
            type_scores[kind] = score
            reasons += [n for r in valid for n in r.notes]

        usable = sum(1 for r in sensors if r.usable)
        if not type_scores:
            fl = {f for r in sensors for f in r.flags}
            if "NO_BASELINE" in fl:
                status = "POST_REPAIR" if np.isfinite(reset_t) else "WARMING_UP"
            else:
                status = "NO_VALID_DATA"
            return MachineRisk(machine, at, 0.0, "LOW", status, usable, len(sensors), flags, reasons)

        ordered = sorted(type_scores.values(), reverse=True)
        score = ordered[0] + (p.corroboration_weight * max(0.0, ordered[1] - p.corroboration_floor)
                              if len(ordered) > 1 else 0.0)
        score = round(float(min(100.0, score)), 1)
        band = "HIGH" if score >= p.warn_threshold else "MEDIUM" if score >= p.medium_threshold else "LOW"
        return MachineRisk(machine, at, score, band, "OK", usable, len(sensors), flags, reasons)

    def score_grid(self, times) -> pd.DataFrame:
        rows = []
        for at in times:
            for m in self.machines:
                r = self.score_machine(m, at)
                rows.append(dict(machine_id=r.machine_id, scored_at=r.at, score=r.score, band=r.band, status=r.status,
                                 usable_sensors=r.n_usable_sensors, sensors=r.n_sensors,
                                 flags="; ".join(r.flags), reasons="; ".join(r.reasons[:3])))
        return pd.DataFrame(rows)
