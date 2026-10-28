"""Deterministic, zero-padded, immutable ID builders (see docs/design_decisions.md)."""
from datetime import datetime, timezone

TS_FORMAT = "%Y%m%dT%H%M%SZ"  # UTC, second precision, e.g. 20260101T000000Z


def plant_id(n: int) -> str:
    return f"PLT-{n:03d}"


def line_id(plant: str, n: int) -> str:
    return f"LINE-{plant}-{n:03d}"


def machine_id(line: str, n: int) -> str:
    return f"MCH-{line}-{n:03d}"


def sensor_id(machine: str, code: str, n: int) -> str:
    return f"SNS-{machine}-{code}-{n:02d}"


def telemetry_id(sensor: str, ts: datetime, dup_seq: int = 0) -> str:
    """First reading in a given second has no suffix. A 2nd, 3rd... reading from the same
    sensor in the same second gets -01, -02... so IDs never collide."""
    base = f"TEL-{sensor}-{ts.astimezone(timezone.utc).strftime(TS_FORMAT)}"
    return base if dup_seq == 0 else f"{base}-{dup_seq:02d}"


def work_order_id(year: int, n: int) -> str:
    return f"WO-{year}-{n:06d}"


# ---- Phase 3A ----
SHIFT_LETTER = {"MORNING": "M", "AFTERNOON": "A", "NIGHT": "N"}


def technician_id(n: int) -> str:
    return f"TECH-{n:03d}"


def part_id(n: int) -> str:
    return f"PRT-{n:04d}"


def failure_id(machine: str, n: int) -> str:
    return f"FAIL-{machine}-{n:03d}"


def shift_id(machine: str, shift_date: datetime, shift_name: str) -> str:
    return f"SHF-{machine}-{shift_date.strftime('%Y%m%d')}-{SHIFT_LETTER[shift_name]}"


def _history_id(prefix: str, parent: str, ts: datetime) -> str:
    return f"{prefix}-{parent}-{ts.astimezone(timezone.utc).strftime(TS_FORMAT)}"


def machine_state_history_id(machine: str, ts: datetime) -> str:
    return _history_id("MSH", machine, ts)


def sensor_status_history_id(sensor: str, ts: datetime) -> str:
    return _history_id("SSH", sensor, ts)


def work_order_status_history_id(work_order: str, ts: datetime) -> str:
    return _history_id("WSH", work_order, ts)
