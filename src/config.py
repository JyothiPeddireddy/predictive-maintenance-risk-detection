"""Generator configuration. The starter and full runs use the SAME code; only these numbers differ."""
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class GeneratorConfig:
    seed: int = 20261022
    n_plants: int = 1
    n_lines: int = 2
    n_machines: int = 4
    sensors_per_machine: int = 2
    days: int = 2
    sampling_interval_s: int = 600
    start_utc: str = "2026-01-01T00:00:00+00:00"
    batch_size: int = 50_000
    output_dir: str = "output/starter"
    # ---- Phase 3B scenario settings. All default to 0 = OFF, so starter.json / full.json behave exactly as before.
    n_technicians: int = 0        # technicians created (round-robin over plants)
    n_failures: int = 0           # machines that develop a failure (at most one failure per machine)
    n_sensor_faults: int = 0      # sensors with a drift / flatline / dropout episode
    n_benign_events: int = 0      # harmless transient surges on healthy machines (false-alarm traps)
    pm_interval_days: int = 0     # preventive maintenance every N days per machine (0 = none)

    @property
    def start(self) -> datetime:
        return datetime.fromisoformat(self.start_utc)

    @property
    def scenarios_enabled(self) -> bool:
        return any((self.n_technicians, self.n_failures, self.n_sensor_faults,
                    self.n_benign_events, self.pm_interval_days))

    @property
    def end(self) -> datetime:
        return self.start + timedelta(seconds=self.readings_per_sensor * self.sampling_interval_s)

    @property
    def readings_per_sensor(self) -> int:
        return self.days * 86400 // self.sampling_interval_s


def load_config(path: str | Path) -> GeneratorConfig:
    with open(path, encoding="utf-8") as f:
        return GeneratorConfig(**json.load(f))
