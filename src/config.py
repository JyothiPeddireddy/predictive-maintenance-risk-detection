"""Generator configuration. The starter and full runs use the SAME code; only these numbers differ."""
import json
from dataclasses import dataclass
from datetime import datetime
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

    @property
    def start(self) -> datetime:
        return datetime.fromisoformat(self.start_utc)

    @property
    def readings_per_sensor(self) -> int:
        return self.days * 86400 // self.sampling_interval_s


def load_config(path: str | Path) -> GeneratorConfig:
    with open(path, encoding="utf-8") as f:
        return GeneratorConfig(**json.load(f))
