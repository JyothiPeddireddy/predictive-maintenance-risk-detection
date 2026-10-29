"""Phase 4 tests: the risk engine (leakage guards, point-in-time rule, sensor quality, behaviour on scenarios).

Only TUNING seeds are used here. The holdout seeds are used only by `python -m src.cli evaluate-holdout`.
"""
import ast
import re
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from src import cli
from src.config import load_config
from src.evaluation.runner import HOLDOUT_SEEDS, TUNING_SEEDS, scoring_times, score_inputs
from src.evaluation.truth import synthetic_dataset
from src.generator.hierarchy import build_hierarchy
from src.generator.pipeline import load_dataset
from src.generator.scenarios import plan_scenarios
from src.risk.data import COLUMNS, RiskInputs, inputs_from_db, truncate_inputs, validate_inputs
from src.risk.engine import RiskEngine, RiskParams

RISK_DIR = Path("src/risk")
P = RiskParams()


@pytest.fixture(scope="module")
def cfg():
    return load_config("config/dev_scenarios.json")      # seed 20261028 = first TUNING seed


@pytest.fixture(scope="module")
def data(cfg):
    return synthetic_dataset(cfg)


@pytest.fixture(scope="module")
def inputs(data):
    return data[0]


@pytest.fixture(scope="module")
def truth(data):
    return data[1]


@pytest.fixture(scope="module")
def plan(cfg):
    return plan_scenarios(cfg, build_hierarchy(cfg))


@pytest.fixture(scope="module")
def engine_(inputs):
    return RiskEngine(inputs, P)


@pytest.fixture(scope="module")
def scores(inputs, cfg):
    s = score_inputs(inputs, P, cfg.start, cfg.end)
    s["scored_at"] = pd.to_datetime(s["scored_at"], utc=True)
    return s


# =====================================================================================
# Target leakage guards
# =====================================================================================
FORBIDDEN_WORDS = ["failure_event", "failureevent", "failure_id", "failure_at", "symptom_onset", "detected_at",
                   "resolved_at", "onset", "scenario", "category", "gain", "ground", "truth", "src.evaluation",
                   "src.generator", "src.models"]


def test_risk_source_never_mentions_failure_labels_or_ground_truth():
    for path in RISK_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        hits = [w for w in FORBIDDEN_WORDS if w in text]
        assert not hits, f"{path} mentions forbidden names {hits}"


def test_risk_package_imports_nothing_from_evaluation_generator_or_models():
    for path in RISK_DIR.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            for m in mods:
                assert not re.match(r"src\.(evaluation|generator|models)", m), f"{path} imports {m}"


def test_risk_inputs_have_exactly_the_allowed_columns(inputs):
    validate_inputs(inputs)
    for name, cols in COLUMNS.items():
        assert list(getattr(inputs, name).columns) == cols
    blocked = {"failure_id", "failure_category", "symptom_onset_at", "failure_at", "findings", "corrective_action"}
    for name in COLUMNS:
        assert not blocked & set(getattr(inputs, name).columns)


def test_an_extra_label_column_is_rejected(inputs):
    bad = RiskInputs(inputs.sensors, inputs.telemetry, inputs.sensor_status,
                     inputs.work_orders.assign(failure_id="FAIL-X"))
    with pytest.raises(ValueError):
        validate_inputs(bad)


# =====================================================================================
# Point-in-time rule: the future must never change a past score
# =====================================================================================
def test_scores_do_not_change_when_future_data_is_removed(inputs, engine_, cfg, truth):
    f = truth.iloc[0]
    probe_times = [f.failure_at - pd.Timedelta(hours=h) for h in (60, 30, 6)] + \
                  [f.returned_to_service + pd.Timedelta(hours=30), cfg.start + pd.Timedelta(days=10)]
    for t in probe_times:
        cut = RiskEngine(truncate_inputs(inputs, t), P)
        for machine in engine_.machines:
            full, short = engine_.score_machine(machine, t), cut.score_machine(machine, t)
            assert (full.score, full.status, full.flags) == (short.score, short.status, short.flags), (machine, t)


def test_scoring_is_deterministic(inputs, cfg):
    t = [cfg.start + pd.Timedelta(days=12)]
    a = RiskEngine(inputs, P).score_grid(t)
    b = RiskEngine(inputs, P).score_grid(t)
    assert a.equals(b)


# =====================================================================================
# Behaviour
# =====================================================================================
def test_scores_stay_in_range_and_use_known_statuses(scores):
    assert scores.score.between(0, 100).all()
    assert set(scores.status) <= {"OK", "WARMING_UP", "POST_REPAIR", "NO_VALID_DATA"}


def test_first_days_are_warming_up_with_score_zero(scores, cfg):
    early = scores[scores.scored_at < cfg.start + pd.Timedelta(days=3)]
    assert len(early) and (early.status == "WARMING_UP").all() and (early.score == 0).all()


def test_healthy_machines_do_not_alarm(scores, truth, plan):
    quiet = scores[~scores.machine_id.isin(set(truth.machine_id) | {x.machine_id for x in plan.sensor_faults})]
    assert quiet.machine_id.nunique() >= 3
    assert quiet.score.max() < P.medium_threshold


def test_benign_surges_stay_below_the_warning_threshold(scores, plan, truth):
    checked = 0
    for b in plan.benign:
        if b.machine_id in set(truth.machine_id):
            continue
        w = scores[(scores.machine_id == b.machine_id) & (scores.scored_at >= b.start)
                   & (scores.scored_at <= b.end + pd.Timedelta(hours=24))]
        assert w.score.max() < P.warn_threshold
        checked += 1
    assert checked >= 2


def test_most_failures_are_warned_about_in_the_72h_before(scores, truth):
    hits = 0
    for f in truth.itertuples():
        w = scores[(scores.machine_id == f.machine_id) & (scores.scored_at < f.failure_at)
                   & (scores.scored_at >= f.failure_at - pd.Timedelta(hours=72))]
        hits += bool((w.score >= P.warn_threshold).any())
    assert hits >= len(truth) - 2          # regression guard on a tuning seed, not a performance claim


def test_degradation_raises_the_score_over_time(scores, truth):
    rising = 0
    for f in truth.itertuples():
        m = scores[scores.machine_id == f.machine_id]
        before = m[m.scored_at < f.onset].score.max()
        late = m[(m.scored_at >= f.failure_at - pd.Timedelta(hours=24)) & (m.scored_at < f.failure_at)].score.max()
        rising += late > before
    assert rising >= len(truth) - 1


def test_repaired_machines_are_not_judged_by_their_past(scores, truth):
    for f in truth.itertuples():
        w = scores[(scores.machine_id == f.machine_id) & (scores.scored_at >= f.returned_to_service + pd.Timedelta(hours=1))
                   & (scores.scored_at <= f.returned_to_service + pd.Timedelta(days=2))]
        assert len(w) and w.score.max() < P.warn_threshold
        assert set(w.status) <= {"POST_REPAIR", "OK"}


def test_faulty_sensors_are_excluded_by_the_quality_rules(engine_, plan):
    seen = {"DROPOUT": 0, "FLATLINE": 0, "DRIFT": 0}
    for x in plan.sensor_faults:
        at = x.start + (x.end - x.start) * 0.8
        flags = [f for f in engine_.score_machine(x.machine_id, at).flags if f.startswith(x.sensor_id[-10:])]
        if x.fault_type == "DROPOUT":
            assert any("DROPOUT" in f for f in flags)
        elif x.fault_type == "FLATLINE":
            assert any("FLATLINE" in f for f in flags)
        else:                                                    # drift: caught by the FAULTY status flag or sibling check
            assert flags
        seen[x.fault_type] += 1
    assert all(seen.values())


def test_a_dropped_out_sensor_does_not_create_a_false_alarm(scores, plan, truth):
    for x in plan.sensor_faults:
        if x.machine_id in set(truth.machine_id):
            continue
        w = scores[(scores.machine_id == x.machine_id) & (scores.scored_at >= x.start)
                   & (scores.scored_at <= x.end + pd.Timedelta(hours=12))]
        assert w.score.max() < P.warn_threshold


def test_preventive_maintenance_does_not_trigger_warnings(scores, plan, truth):
    healthy = set(scores.machine_id) - set(truth.machine_id)
    pm = [p for p in plan.preventive if p.machine_id in healthy]
    assert len(pm) > 5
    for p in pm:
        w = scores[(scores.machine_id == p.machine_id) & (scores.scored_at >= p.started_at)
                   & (scores.scored_at <= p.completed_at + pd.Timedelta(hours=12))]
        assert w.score.max() < P.warn_threshold


def test_seed_sets_are_disjoint():
    assert not set(TUNING_SEEDS) & set(HOLDOUT_SEEDS)
    assert len(HOLDOUT_SEEDS) >= 10


# =====================================================================================
# Database path
# =====================================================================================
@pytest.fixture(scope="module")
def risk_db(engine, cfg, tmp_path_factory):
    c = replace(cfg, output_dir=str(tmp_path_factory.mktemp("risk_manifest")))
    load_dataset(engine, c, reset=True)
    try:
        yield engine
    finally:
        load_dataset(engine, load_config("config/starter.json"), reset=True)


def test_database_inputs_have_only_allowed_columns_and_give_the_same_scores(risk_db, inputs, cfg):
    db_inputs = inputs_from_db(risk_db)
    for name, cols in COLUMNS.items():
        assert list(getattr(db_inputs, name).columns) == cols
    times = [cfg.start + pd.Timedelta(days=d, hours=h) for d in (8, 15, 25, 36) for h in (3, 15)]
    a = RiskEngine(db_inputs, P).score_grid(times)
    b = RiskEngine(inputs, P).score_grid(times)
    pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True))


def test_cli_score_report_and_evaluate_write_files(risk_db, tmp_path, monkeypatch, capsys):
    name = risk_db.url.database
    for argv, expected in (
            (["--db", name, "score", "--out", str(tmp_path / "scores.csv")], ["scores.csv"]),
            (["--db", name, "report", "--out-dir", str(tmp_path)], ["machine_risk_report.csv", "maintenance_downtime_summary.csv"]),
            (["--db", name, "evaluate", "--out-dir", str(tmp_path)], [f"evaluation_{name}.md", "evaluation_per_failure.csv"])):
        monkeypatch.setattr(sys, "argv", ["cli", *argv])
        cli.main()
        for f in expected:
            assert (tmp_path / f).exists() and (tmp_path / f).stat().st_size > 0, f
    report = pd.read_csv(tmp_path / "maintenance_downtime_summary.csv")
    assert len(report) == 12 and report.corrective_orders.sum() == 6
    assert "Precision" in (tmp_path / f"evaluation_{name}.md").read_text(encoding="utf-8")


def test_cli_evaluate_explains_when_the_database_has_no_failures(engine, tmp_path, monkeypatch):
    """The plain starter data has no failure records: evaluate must say so, not crash. (Runs last in this file.)"""
    load_dataset(engine, load_config("config/starter.json"), reset=True)
    monkeypatch.setattr(sys, "argv", ["cli", "--db", engine.url.database, "evaluate", "--out-dir", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert "no failure records" in str(exc.value)
