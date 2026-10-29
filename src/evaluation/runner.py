"""Glue: score a dataset, evaluate it, write reports.

Seeds are split on purpose:
  TUNING_SEEDS   the only data used to choose the rule parameters / warning threshold.
  HOLDOUT_SEEDS  never used for tuning; they give the honest test result.
Both are SYNTHETIC datasets made by the same generator (src/generator), so even the holdout result says nothing
about real machines (see docs/risk_and_evaluation.md).
"""
from dataclasses import replace
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.config import GeneratorConfig
from src.evaluation import metrics as M
from src.evaluation.truth import synthetic_dataset, truth_from_db
from src.risk.data import RiskInputs, inputs_from_db
from src.risk.engine import RiskEngine, RiskParams

TUNING_SEEDS = (20261028, 20261029, 20261030, 20261031, 20261032)
HOLDOUT_SEEDS = tuple(range(7000001, 7000011))
FIRST_SCORE_DAY = 1


def _utc(ts) -> pd.Timestamp:
    """Any timestamp -> UTC. (PostgreSQL returns times in the computer's own time zone, e.g. +05:30 in India.)"""
    ts = pd.Timestamp(ts)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def scoring_times(cfg_start, cfg_end, every_hours: float = 3.0) -> pd.DatetimeIndex:
    return pd.date_range(_utc(cfg_start) + pd.Timedelta(days=FIRST_SCORE_DAY),
                         _utc(cfg_end) - pd.Timedelta(hours=every_hours), freq=f"{every_hours}h")


def score_inputs(inputs: RiskInputs, params: RiskParams, start, end, every_hours: float = 3.0) -> pd.DataFrame:
    return RiskEngine(inputs, params).score_grid(scoring_times(start, end, every_hours))


def evaluate_seeds(cfg: GeneratorConfig, seeds, params: RiskParams, every_hours: float = 3.0) -> list[dict]:
    """In-memory (no database): generate each seed's dataset, score it, evaluate it."""
    out = []
    for seed in seeds:
        c = replace(cfg, seed=seed)
        inputs, truth = synthetic_dataset(c)
        scores = score_inputs(inputs, params, c.start, c.end, every_hours)
        r = M.evaluate(scores, truth, params.warn_threshold, step_hours=every_hours)
        r["seed"] = seed
        out.append(r)
    return out


def evaluate_database(engine: Engine, params: RiskParams, every_hours: float = 3.0):
    inputs = inputs_from_db(engine)
    with engine.connect() as c:
        start, end = c.execute(text("SELECT min(event_ts), max(event_ts) FROM telemetry_event")).one()
    end = _utc(end) + pd.Timedelta(hours=every_hours)   # last reading is the last scoring time
    scores = score_inputs(inputs, params, start, end, every_hours)
    truth = truth_from_db(engine)
    return scores, truth, M.evaluate(scores, truth, params.warn_threshold, step_hours=every_hours)


# ---------------------------------------------------------------- reports
def machine_risk_report(scores: pd.DataFrame, at=None) -> pd.DataFrame:
    df = scores.copy()
    df["scored_at"] = pd.to_datetime(df["scored_at"], utc=True)
    if at is None:
        at = df["scored_at"].max()
    else:
        at = pd.Timestamp(at)
        at = at.tz_localize("UTC") if at.tzinfo is None else at.tz_convert("UTC")
    snap = df[df["scored_at"] == df.loc[df["scored_at"] <= at, "scored_at"].max()]
    return snap.sort_values("score", ascending=False)[
        ["machine_id", "scored_at", "score", "band", "status", "usable_sensors", "sensors", "flags", "reasons"]]


DOWNTIME_SQL = """
SELECT m.machine_id,
       count(*) FILTER (WHERE w.maintenance_type = 'CORRECTIVE') AS corrective_orders,
       count(*) FILTER (WHERE w.maintenance_type = 'PREVENTIVE') AS preventive_orders,
       count(*) FILTER (WHERE w.maintenance_type = 'INSPECTION') AS inspection_orders,
       round(coalesce(sum(extract(epoch FROM (w.returned_to_service_at - w.downtime_start)) / 3600.0)
             FILTER (WHERE w.maintenance_type = 'CORRECTIVE'), 0)::numeric, 1) AS corrective_downtime_h,
       round(coalesce(sum(extract(epoch FROM (w.returned_to_service_at - w.downtime_start)) / 3600.0)
             FILTER (WHERE w.maintenance_type = 'PREVENTIVE'), 0)::numeric, 1) AS preventive_downtime_h,
       coalesce((SELECT round(sum(wp.quantity_used * p.unit_cost), 2) FROM work_order_part wp
                 JOIN part p USING (part_id) JOIN maintenance_work_order w2 USING (work_order_id)
                 WHERE w2.machine_id = m.machine_id), 0) AS parts_cost
FROM machine m LEFT JOIN maintenance_work_order w USING (machine_id)
GROUP BY m.machine_id ORDER BY m.machine_id"""


def downtime_summary(engine: Engine) -> pd.DataFrame:
    with engine.connect() as c:
        return pd.DataFrame(c.execute(text(DOWNTIME_SQL)).mappings().all())


def md_table(df: pd.DataFrame) -> str:
    """Tiny markdown table writer (avoids needing the 'tabulate' package)."""
    cols = list(df.columns)
    lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join("n/a" if (isinstance(v, float) and v != v) else str(v) for v in row) + " |")
    return "\n".join(lines)


def _fmt(x, pct=False):
    if x is None or (isinstance(x, float) and x != x):
        return "n/a"
    return f"{x:.1%}" if pct else f"{x:.1f}" if isinstance(x, float) else str(x)


def metrics_table(m: dict) -> str:
    rows = [("Scored (machine, time) pairs", m["scored_pairs"]), ("Positive pairs (failure within 72 h)", m["positives"]),
            ("Confusion: TP / FP / FN / TN", f'{m["tp"]} / {m["fp"]} / {m["fn"]} / {m["tn"]}'),
            ("Precision", _fmt(m["precision"], True)), ("Recall", _fmt(m["recall"], True)), ("F1", _fmt(m["f1"], True)),
            ("Failures detected (event recall)", f'{m["failures_detected"]} of {m["failures"]} ({_fmt(m["event_recall"], True)})'),
            ("Median warning lead time (h, max 72)", _fmt(m["median_lead_time_h"])),
            ("Warning episodes / false episodes", f'{m["warning_episodes"]} / {m["false_episodes"]}'),
            ("False episodes per machine-month", "n/a" if m.get("false_episodes_per_machine_month") is None or m["false_episodes_per_machine_month"] != m["false_episodes_per_machine_month"] else f'{m["false_episodes_per_machine_month"]:.2f}'),
            ("Failures that also had an EARLIER warning (>72 h ahead)", m["failures_with_early_warning"])]
    return "| Measure | Value |\n|---|---|\n" + "\n".join(f"| {a} | {b} |" for a, b in rows)


def write_holdout_report(path: Path, params: RiskParams, tuning: list[dict], holdout: list[dict] | None) -> None:
    sections = ["# Risk engine evaluation (synthetic data)\n",
                f"Warning threshold: **{params.warn_threshold:g}** (score 0-100). Horizon: 72 h. "
                "All data is SYNTHETIC, produced by this project's own generator.\n"]
    for title, res in (("Tuning seeds (used to choose the rules and threshold; optimistic)", tuning),
                       ("Holdout seeds (never used for tuning; the honest test)", holdout)):
        if not res:
            continue
        pooled = M.pool(res)
        sections.append(f"## {title}\nSeeds: {', '.join(str(r['seed']) for r in res)}\n\n{metrics_table(pooled)}\n")
        sections.append("By failure category:\n\n" + md_table(M.by_category(pooled["per_failure"]).round(1)) + "\n")
        strength = M.by_signal_strength(pooled["per_failure"])
        if len(strength):
            sections.append("By injected signal strength:\n\n" + md_table(strength) + "\n")
        per_seed = pd.DataFrame([{k: r[k] for k in ("seed", "precision", "recall", "f1", "failures", "failures_detected",
                                                    "median_lead_time_h", "false_episodes")} for r in res])
        sections.append("Per seed:\n\n" + md_table(per_seed.round(3)) + "\n")
    sections.append(LIMITS)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(sections), encoding="utf-8")


LIMITS = """## How to read these numbers (limits)
- **Synthetic, not real.** The failures were injected by this project's generator, and the rules were designed to
  recognise exactly that kind of pattern (rising level, trend, bursts). Real machines are messier, so real-world
  performance would almost certainly be lower. Validation on real industrial data has NOT been done.
- **Holdout is only partly independent.** Holdout seeds are new random datasets from the same generator and the same
  failure mechanisms. They protect against over-fitting the thresholds, not against a mismatch with reality.
- **Strict labels.** A warning more than 72 h before a failure counts as a false positive in precision/recall even
  when the machine really was degrading; those cases are listed as "earlier warning".
- **Lead time is capped at 72 h** by definition (first warning inside the 72 h window).
- Scores are computed every 3 h; consecutive scoring times are strongly correlated, so precision/recall are not
  independent samples. Event recall (a few dozen failures) is the more meaningful number, and its uncertainty is large.
"""
