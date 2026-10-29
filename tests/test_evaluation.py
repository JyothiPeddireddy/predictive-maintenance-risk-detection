"""Tests of the evaluation maths with tiny hand-made examples (no database, no generator)."""
from datetime import timedelta, timezone

import pandas as pd
import pytest

from src.evaluation import metrics as M

T0 = pd.Timestamp("2026-01-10", tz="UTC")
STEP = pd.Timedelta(hours=3)
FAIL = T0 + pd.Timedelta(days=10)


def grid(machine="M1", days=20, score=0.0):
    times = pd.date_range(T0, T0 + pd.Timedelta(days=days), freq="3h", inclusive="left")
    return pd.DataFrame(dict(machine_id=machine, scored_at=times, score=score))


def truth(machine="M1", failure_at=FAIL, down_h=10):
    return pd.DataFrame([dict(failure_id="F1", machine_id=machine, category="BEARING_WEAR",
                              onset=failure_at - pd.Timedelta(days=5), failure_at=failure_at,
                              returned_to_service=failure_at + pd.Timedelta(hours=down_h), gain=1.0)])


def test_labels_cover_exactly_the_72_hours_before_the_failure():
    df = M.add_labels(grid(), truth())
    pos = df[df.label]
    assert len(pos) == 24                                              # 72 h / 3 h
    assert pos.scored_at.min() == FAIL - pd.Timedelta(hours=72) + STEP * 0 and pos.scored_at.max() == FAIL - STEP
    assert not df[df.scored_at == FAIL].label.any()                    # at the failure itself: not "before"


def test_times_while_the_machine_is_down_are_excluded():
    df = M.add_labels(grid(), truth(down_h=10))
    gone = df[df.excluded]
    assert gone.scored_at.min() == FAIL
    assert gone.scored_at.max() <= FAIL + pd.Timedelta(hours=10 + 24)
    assert (df[df.scored_at > FAIL + pd.Timedelta(hours=40)].excluded == False).all()  # noqa: E712


def test_perfect_scores_give_perfect_metrics():
    g = grid()
    lab = M.add_labels(g, truth())
    g["score"] = lab.label.map({True: 100.0, False: 0.0}).to_numpy()
    r = M.evaluate(g, truth(), 50, step_hours=3)
    assert (r["precision"], r["recall"], r["f1"], r["event_recall"]) == (1, 1, 1, 1)
    assert (r["fp"], r["fn"]) == (0, 0) and r["tp"] == 24
    assert r["median_lead_time_h"] == 72 and r["false_episodes"] == 0


def test_silent_engine_scores_zero_recall():
    r = M.evaluate(grid(), truth(), 50, step_hours=3)
    assert r["recall"] == 0 and r["event_recall"] == 0 and r["tp"] == 0 and r["fn"] == 24
    assert r["precision"] != r["precision"]                           # NaN: no warnings were raised


def test_threshold_is_inclusive_and_confusion_matrix_adds_up():
    g = grid(score=10.0)
    g.loc[g.scored_at >= FAIL - pd.Timedelta(hours=12), "score"] = 50.0
    r = M.evaluate(g, truth(), 50, step_hours=3)
    assert r["tp"] == 4 and r["fn"] == 20                              # last 12 h = 4 scoring times
    assert r["tp"] + r["fp"] + r["fn"] + r["tn"] == r["scored_pairs"]
    assert 9 < r["median_lead_time_h"] <= 12


def test_false_episodes_are_counted_per_run_of_warnings():
    g = grid()
    for start in (2, 6):                                               # two separate bursts of warnings, days before the risk window
        g.loc[(g.scored_at >= T0 + pd.Timedelta(days=start)) & (g.scored_at < T0 + pd.Timedelta(days=start, hours=9)), "score"] = 80.0
    lab = M.add_labels(g, truth())
    g.loc[lab.label, "score"] = 80.0                                   # one real episode inside the window
    r = M.evaluate(g, truth(), 50, step_hours=3)
    assert r["warning_episodes"] == 3 and r["false_episodes"] == 2
    assert r["false_episodes_per_machine_month"] == pytest.approx(2 / r["machine_days"] * 30)


def test_warnings_earlier_than_72h_count_as_early_not_as_detection():
    g = grid()
    g.loc[(g.scored_at >= FAIL - pd.Timedelta(days=4)) & (g.scored_at < FAIL - pd.Timedelta(days=3, hours=12)), "score"] = 90.0
    r = M.evaluate(g, truth(), 50, step_hours=3)
    assert r["event_recall"] == 0 and r["failures_with_early_warning"] == 1 and r["false_episodes"] == 1


def test_other_machines_do_not_leak_into_a_machines_labels():
    g = pd.concat([grid("M1"), grid("M2", score=100.0)], ignore_index=True)
    r = M.evaluate(g, truth("M1"), 50, step_hours=3)
    assert r["tp"] == 0 and r["fp"] > 0                                # M2 never fails, so all its warnings are false
    assert r["false_episodes"] == 1


def test_pooling_adds_counts_and_recomputes_ratios():
    a = M.evaluate(grid(), truth(), 50, step_hours=3)
    g = grid(); g.loc[M.add_labels(g, truth()).label, "score"] = 100.0
    b = M.evaluate(g, truth(), 50, step_hours=3)
    p = M.pool([a, b])
    assert p["tp"] == a["tp"] + b["tp"] and p["failures"] == 2 and p["failures_detected"] == 1
    assert p["recall"] == pytest.approx(24 / 48) and p["event_recall"] == 0.5


def test_scoring_times_accept_timestamps_in_any_time_zone():
    """Regression: on a computer set to India time PostgreSQL returns +05:30 timestamps."""
    from src.evaluation.runner import scoring_times
    ist = timezone(timedelta(hours=5, minutes=30))                         # fixed +05:30 (no tz database needed)
    start = pd.Timestamp("2026-01-01 05:30", tz=ist)                       # = 2026-01-01 00:00 UTC
    end = pd.Timestamp("2026-01-04 05:30", tz=ist)
    local = scoring_times(start, end)
    utc = scoring_times(start.tz_convert("UTC"), end.tz_convert("UTC"))
    assert list(local) == list(utc) and str(local.tz) == "UTC"
    assert local[0] == pd.Timestamp("2026-01-02 00:00", tz="UTC")
    naive = scoring_times(pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-04"))   # naive = treated as UTC
    assert list(naive) == list(utc)


def test_evaluating_without_any_failures_does_not_crash():
    empty = truth().iloc[0:0]
    r = M.evaluate(grid(), empty, 50, step_hours=3)
    assert r["failures"] == 0 and r["tp"] == 0 and r["fn"] == 0
    assert r["event_recall"] != r["event_recall"]                      # NaN: there is nothing to detect
    assert M.by_category(r["per_failure"]).empty
