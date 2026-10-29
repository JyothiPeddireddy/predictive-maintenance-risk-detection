"""Phase 3B: turns a ScenarioPlan into rows for the Phase 3A tables.

Builds (all deterministic from cfg.seed): technician, part, failure_event, maintenance_work_order,
work_order_technician, work_order_part, machine_state_history, sensor_status_history,
work_order_status_history and operating_shift.

Every row is built so the database CHECK constraints accept it; the tests prove this by loading it.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

import numpy as np

from src.config import GeneratorConfig
from src.generator import ids
from src.generator.scenarios import ScenarioPlan

SCHEDULE_IDLE_UNTIL_HOUR = 6   # same rule as the healthy baseline: idle 00:00-05:59 UTC

# (part_id, part_number, name, category, unit, unit_cost)
PARTS = [
    (1, "BRG-6204", "Ball bearing 6204", "BEARING", "EA", "12.50"),
    (2, "BRG-NU210", "Roller bearing NU210", "BEARING", "EA", "48.00"),
    (3, "SEAL-45", "Shaft seal 45 mm", "SEAL", "EA", "6.75"),
    (4, "MOT-FAN-037", "Cooling fan motor 0.37 kW", "MOTOR", "EA", "185.00"),
    (5, "FLT-AIR-01", "Air filter element", "FILTER", "EA", "22.00"),
    (6, "LUB-EP2", "Bearing grease EP2", "LUBRICANT", "KG", "14.20"),
    (7, "LUB-ISO46", "Hydraulic oil ISO 46", "LUBRICANT", "L", "3.80"),
    (8, "ELC-CONT-25", "Contactor 25 A", "ELECTRICAL", "EA", "31.00"),
    (9, "ELC-WIND-KIT", "Motor winding repair kit", "ELECTRICAL", "EA", "260.00"),
    (10, "BLT-B52", "V-belt B52", "BELT", "EA", "9.90"),
    (11, "SNS-RTD", "RTD temperature probe", "SENSOR", "EA", "27.00"),
    (12, "SNS-ACC", "Accelerometer ICP", "SENSOR", "EA", "95.00"),
    (13, "CPL-INS", "Coupling insert", "OTHER", "EA", "18.00"),
]
NAMES = ["Asha Rao", "Ravi Kumar", "Meera Nair", "Imran Shaikh", "Priya Menon", "Arjun Reddy",
         "Kavya Iyer", "Sanjay Patil", "Neha Gupta", "Vikram Singh"]
SPECIALTIES = ["MECHANICAL", "ELECTRICAL", "INSTRUMENTATION", "GENERAL"]

# which specialty should lead the repair (first choice first) and which parts are used
CATEGORY_PREFS = {"BEARING_WEAR": ["MECHANICAL", "GENERAL"], "OVERHEATING": ["MECHANICAL", "GENERAL"],
                  "LUBRICATION": ["MECHANICAL", "GENERAL"], "MISALIGNMENT": ["MECHANICAL", "GENERAL"],
                  "ELECTRICAL": ["ELECTRICAL", "GENERAL"]}
CATEGORY_TEXT = {
    "BEARING_WEAR": ("Rising vibration and temperature; worn bearing found.", "Replaced bearing and re-greased."),
    "OVERHEATING": ("Sustained high temperature; cooling fan degraded, filter clogged.", "Replaced cooling fan motor and filter."),
    "LUBRICATION": ("Dry bearing housing, noisy vibration.", "Re-lubricated and replaced shaft seals."),
    "MISALIGNMENT": ("Shaft misalignment with periodic vibration.", "Realigned shaft, replaced coupling insert and belt."),
    "ELECTRICAL": ("Intermittent electrical faults and heat spikes.", "Replaced contactor and checked windings."),
}
PRIORITY = {"MINOR": "MEDIUM", "MAJOR": "HIGH", "CRITICAL": "URGENT"}


@dataclass
class _Interval:
    start: datetime
    end: datetime
    state: str          # FAILED | MAINTENANCE
    source: str         # FAILURE | WORK_ORDER
    work_order_id: str | None = None
    failure_id: str | None = None


def _dec(x: float, places: int = 2) -> Decimal:
    return Decimal(str(round(x, places)))


def _schedule_state(ts: datetime) -> str:
    return "IDLE" if ts.hour < SCHEDULE_IDLE_UNTIL_HOUR else "RUNNING"


def build_records(cfg: GeneratorConfig, h: dict, plan: ScenarioPlan) -> dict[str, list[dict]]:
    rng = np.random.default_rng(np.random.SeedSequence([cfg.seed, 9003]))
    plant_of_machine = {}
    line_plant = {l["line_id"]: l["plant_id"] for l in h["lines"]}
    for m in h["machines"]:
        plant_of_machine[m["machine_id"]] = line_plant[m["line_id"]]
    plants = [p["plant_id"] for p in h["plants"]]
    sensor_by_id = {s["sensor_id"]: s for s in h["sensors"]}

    # ---------------- technicians and parts ----------------
    techs = []
    for i in range(cfg.n_technicians):
        status = "ON_LEAVE" if (cfg.n_technicians >= 6 and i == cfg.n_technicians - 1) else "ACTIVE"
        techs.append(dict(technician_id=ids.technician_id(i + 1), plant_id=plants[i % len(plants)],
                          full_name=NAMES[i % len(NAMES)] + (f" {i // len(NAMES) + 2}" if i >= len(NAMES) else ""),
                          specialty=SPECIALTIES[i % len(SPECIALTIES)], status=status,
                          hired_on=date(2018, 1, 1) + timedelta(days=97 * i)))
    parts = [dict(part_id=ids.part_id(n), part_number=pn, part_name=name, category=cat,
                  unit_of_measure=unit, unit_cost=Decimal(cost), status="ACTIVE")
             for n, pn, name, cat, unit, cost in PARTS]

    # ---------------- work-order drafts ----------------
    drafts = []
    for f in plan.failures:
        text_find, text_fix = CATEGORY_TEXT[f.category]
        parts_used = {
            "BEARING_WEAR": [(2 if f.severity == "CRITICAL" else 1, _dec(1 if f.severity == "CRITICAL" else 2)),
                             (6, _dec(float(rng.uniform(0.3, 0.8))))],
            "OVERHEATING": [(4, _dec(1)), (5, _dec(1))],
            "LUBRICATION": [(6, _dec(float(rng.uniform(1.0, 2.0)))), (3, _dec(2))],
            "MISALIGNMENT": [(13, _dec(1)), (10, _dec(1))],
            "ELECTRICAL": [(8, _dec(1))] + ([(9, _dec(1))] if f.severity == "CRITICAL" else []),
        }[f.category]
        drafts.append(dict(
            kind="FAILURE", machine_id=f.machine_id, failure_id=f.failure_id, maintenance_type="CORRECTIVE",
            priority=PRIORITY[f.severity], created_at=f.wo_created, scheduled_for=None, started_at=f.wo_started,
            completed_at=f.wo_completed, downtime_start=f.failure_at, returned_to_service_at=f.returned_to_service,
            findings=text_find, corrective_action=text_fix, parts=parts_used, prefs=CATEGORY_PREFS[f.category],
            assistant=f.severity != "MINOR"))
    for p in plan.preventive:
        drafts.append(dict(
            kind="PREVENTIVE", machine_id=p.machine_id, failure_id=None, maintenance_type="PREVENTIVE",
            priority="LOW", created_at=p.created_at, scheduled_for=p.scheduled_for, started_at=p.started_at,
            completed_at=p.completed_at, downtime_start=p.started_at, returned_to_service_at=p.completed_at,
            findings="Routine inspection: no abnormalities found.",
            corrective_action="Replaced air filter and topped up lubricant.",
            parts=[(5, _dec(1)), (7, _dec(float(rng.uniform(0.5, 2.0))))], prefs=["GENERAL", "MECHANICAL"],
            assistant=False))
    for sf in plan.sensor_faults:
        part_no = 11 if sf.sensor_type == "TEMP" else 12
        replaced = sf.fault_type != "DROPOUT"
        drafts.append(dict(
            kind="SENSOR", machine_id=sf.machine_id, failure_id=None, maintenance_type="INSPECTION",
            priority="MEDIUM" if sf.fault_type == "DRIFT" else "LOW", created_at=sf.flagged_at, scheduled_for=None,
            started_at=sf.end - timedelta(minutes=45), completed_at=sf.end, downtime_start=None,
            returned_to_service_at=None,
            findings=f"Sensor {sf.sensor_id} flagged FAULTY ({sf.fault_type.lower()}).",
            corrective_action="Replaced sensor." if replaced else "Reseated connector and cable.",
            parts=[(part_no, _dec(1))] if replaced else [], prefs=["INSTRUMENTATION", "GENERAL"], assistant=False))

    drafts.sort(key=lambda d: (d["created_at"], d["machine_id"], d["kind"]))
    for n, d in enumerate(drafts, start=1):
        d["work_order_id"] = ids.work_order_id(d["created_at"].year, n)

    # ---------------- assignments (a technician never works two jobs at once, when avoidable) ----------------
    busy_until = {t["technician_id"]: cfg.start for t in techs}
    bridge_tech, bridge_part, work_orders = [], [], []
    lead_of = {}
    for d in sorted(drafts, key=lambda x: (x["started_at"], x["work_order_id"])):
        plant = plant_of_machine[d["machine_id"]]
        pool = [t for t in techs if t["status"] == "ACTIVE" and t["plant_id"] == plant] or \
               [t for t in techs if t["status"] == "ACTIVE"]
        lead_of[d["work_order_id"]] = None
        if not pool:
            continue

        def pick(exclude=()):
            cands = [t for t in pool if t["technician_id"] not in exclude]
            if not cands:
                return None
            free = [t for t in cands if busy_until[t["technician_id"]] <= d["started_at"]]
            for spec in d["prefs"]:
                match = [t for t in free if t["specialty"] == spec]
                if match:
                    return min(match, key=lambda t: (busy_until[t["technician_id"]], t["technician_id"]))
            if free:
                return min(free, key=lambda t: (busy_until[t["technician_id"]], t["technician_id"]))
            return min(cands, key=lambda t: (busy_until[t["technician_id"]], t["technician_id"]))

        crew = [(pick(), "LEAD", 1.0)]
        if d["assistant"]:
            assistant = pick(exclude={crew[0][0]["technician_id"]})
            if assistant:
                crew.append((assistant, "ASSISTANT", 0.8))
        hours = (d["completed_at"] - d["started_at"]).total_seconds() / 3600
        for tech, role, share in crew:
            tid = tech["technician_id"]
            busy_until[tid] = max(busy_until[tid], d["completed_at"])
            if role == "LEAD":
                lead_of[d["work_order_id"]] = tid
            bridge_tech.append(dict(work_order_id=d["work_order_id"], technician_id=tid, role=role,
                                    assigned_at=d["created_at"] + timedelta(minutes=5),
                                    hours_worked=_dec(hours * share)))

    wo_status_rows = []
    for d in drafts:
        wid = d["work_order_id"]
        work_orders.append(dict(
            work_order_id=wid, machine_id=d["machine_id"], failure_id=d["failure_id"],
            maintenance_type=d["maintenance_type"], priority=d["priority"], status="COMPLETED",
            created_at=d["created_at"], scheduled_for=d["scheduled_for"], started_at=d["started_at"],
            completed_at=d["completed_at"], downtime_start=d["downtime_start"],
            returned_to_service_at=d["returned_to_service_at"], findings=d["findings"],
            corrective_action=d["corrective_action"]))
        for part_no, qty in d["parts"]:
            bridge_part.append(dict(work_order_id=wid, part_id=ids.part_id(part_no), quantity_used=qty,
                                    replaced_at=d["started_at"] + (d["completed_at"] - d["started_at"]) / 2))
        lead = lead_of[wid]
        for prev, new, ts, who in ((None, "OPEN", d["created_at"], None),
                                   ("OPEN", "IN_PROGRESS", d["started_at"], lead),
                                   ("IN_PROGRESS", "COMPLETED", d["completed_at"], lead)):
            wo_status_rows.append(dict(history_id=ids.work_order_status_history_id(wid, ts), work_order_id=wid,
                                       previous_status=prev, new_status=new, changed_at=ts,
                                       changed_by_technician_id=who, note=None))
    wo_of_failure = {d["failure_id"]: d["work_order_id"] for d in drafts if d["kind"] == "FAILURE"}

    # ---------------- failure events ----------------
    failure_rows = []
    for f in plan.failures:
        failure_rows.append(dict(
            failure_id=f.failure_id, machine_id=f.machine_id, failure_category=f.category, severity=f.severity,
            symptom_onset_at=f.onset, failure_at=f.failure_at, detected_at=f.detected_at,
            resolved_at=f.wo_completed, status="RESOLVED",
            description=f"Synthetic {f.category.replace('_', ' ').lower()} scenario (signal gain {f.gain})."))

    # ---------------- machine state history ----------------
    intervals: dict[str, list[_Interval]] = {m["machine_id"]: [] for m in h["machines"]}
    for f in plan.failures:
        wo = wo_of_failure[f.failure_id]
        intervals[f.machine_id].append(_Interval(f.failure_at, f.wo_started, "FAILED", "FAILURE", failure_id=f.failure_id))
        intervals[f.machine_id].append(_Interval(f.wo_started, f.returned_to_service, "MAINTENANCE", "WORK_ORDER", work_order_id=wo))
    for d in drafts:
        if d["kind"] == "PREVENTIVE":
            intervals[d["machine_id"]].append(_Interval(d["started_at"], d["completed_at"], "MAINTENANCE",
                                                        "WORK_ORDER", work_order_id=d["work_order_id"]))
    state_rows = []
    for machine, ivs in intervals.items():
        times = set()
        for day in range(cfg.days):
            base = cfg.start + timedelta(days=day)
            times |= {base, base + timedelta(hours=SCHEDULE_IDLE_UNTIL_HOUR)}
        for iv in ivs:
            times |= {iv.start, iv.end}
        prev = None
        for ts in sorted(x for x in times if cfg.start <= x < cfg.end):
            starting = [iv for iv in ivs if iv.start == ts]
            ending = [iv for iv in ivs if iv.end == ts]
            active = [iv for iv in ivs if iv.start <= ts < iv.end]
            state = active[0].state if active else _schedule_state(ts)
            if state == prev:
                continue
            cause = (starting or ending or [None])[0]
            state_rows.append(dict(
                history_id=ids.machine_state_history_id(machine, ts), machine_id=machine, previous_state=prev,
                new_state=state, changed_at=ts, change_source=cause.source if cause else "SCHEDULE",
                work_order_id=cause.work_order_id if cause and cause.source == "WORK_ORDER" else None,
                failure_id=cause.failure_id if cause and cause.source == "FAILURE" else None))
            prev = state

    # ---------------- sensor status history ----------------
    sensor_rows = [dict(history_id=ids.sensor_status_history_id(s["sensor_id"], cfg.start), sensor_id=s["sensor_id"],
                        previous_status=None, new_status="ACTIVE", changed_at=cfg.start, reason="initial status")
                   for s in h["sensors"]]
    for sf in plan.sensor_faults:
        sensor_rows.append(dict(history_id=ids.sensor_status_history_id(sf.sensor_id, sf.flagged_at),
                                sensor_id=sf.sensor_id, previous_status="ACTIVE", new_status="FAULTY",
                                changed_at=sf.flagged_at, reason=f"{sf.fault_type.lower()} detected"))
        sensor_rows.append(dict(history_id=ids.sensor_status_history_id(sf.sensor_id, sf.end),
                                sensor_id=sf.sensor_id, previous_status="FAULTY", new_status="ACTIVE",
                                changed_at=sf.end, reason="repaired / recalibrated"))

    # ---------------- operating shifts (planned context: NIGHT idle, MORNING + AFTERNOON running) ----------------
    shift_rows = []
    shifts = (("NIGHT", 0, 6, "IDLE"), ("MORNING", 6, 14, "RUNNING"), ("AFTERNOON", 14, 24, "RUNNING"))
    for m in h["machines"]:
        for day in range(cfg.days):
            base = cfg.start + timedelta(days=day)
            for name, a, b, planned in shifts:
                load = _dec(float(rng.uniform(65, 95))) if planned == "RUNNING" else Decimal("0.00")
                shift_rows.append(dict(
                    shift_id=ids.shift_id(m["machine_id"], base, name), machine_id=m["machine_id"],
                    shift_name=name, shift_start=base + timedelta(hours=a), shift_end=base + timedelta(hours=b),
                    planned_state=planned, planned_load_pct=load))

    return {
        "technician": techs, "part": parts, "failure_event": failure_rows,
        "maintenance_work_order": work_orders, "work_order_technician": bridge_tech,
        "work_order_part": bridge_part, "machine_state_history": state_rows,
        "sensor_status_history": sensor_rows, "work_order_status_history": wo_status_rows,
        "operating_shift": shift_rows,
    }
