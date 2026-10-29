"""Evaluation of risk scores against ground truth (evaluation only; the risk engine never imports this).

Definitions (so the numbers can be checked by hand):
  Label        a scoring time t on machine m is POSITIVE if a failure of m happens in (t, t + 72 h].
  Excluded     times when the machine is already down: from the failure until 24 h after it is back in service.
  Prediction   WARNING if score >= threshold.
  Assessment   precision / recall / F1 / confusion matrix over all scored (machine, time) pairs that are not excluded.
  Event recall share of failures with at least one warning in the 72 h before the failure.
  Lead time    failure time minus the FIRST warning inside that 72 h window (so it is at most 72 h).
  Warning episode  a run of consecutive warning times on one machine. It is FALSE if it never touches a positive time.
"""
import numpy as np
import pandas as pd

HORIZON_H = 72.0
RECOVERY_H = 24.0


def add_labels(scores: pd.DataFrame, truth: pd.DataFrame, horizon_h: float = HORIZON_H,
               recovery_h: float = RECOVERY_H) -> pd.DataFrame:
    df = scores.copy()
    df["scored_at"] = pd.to_datetime(df["scored_at"], utc=True)
    df["label"] = False
    df["excluded"] = False
    for f in truth.itertuples(index=False):
        mine = df["machine_id"] == f.machine_id
        ahead = (f.failure_at - df["scored_at"])
        df.loc[mine & (ahead > pd.Timedelta(0)) & (ahead <= pd.Timedelta(hours=horizon_h)), "label"] = True
        down = (df["scored_at"] >= f.failure_at) & (df["scored_at"] <= f.returned_to_service + pd.Timedelta(hours=recovery_h))
        df.loc[mine & down, "excluded"] = True
    return df


def _episodes(df: pd.DataFrame, step: pd.Timedelta) -> list[dict]:
    """Runs of consecutive warnings per machine."""
    out = []
    for m, g in df.sort_values("scored_at").groupby("machine_id"):
        warn = g[g["warn"]]
        if warn.empty:
            continue
        gap = warn["scored_at"].diff() > step * 1.5
        run_id = gap.cumsum()
        for _, r in warn.groupby(run_id):
            out.append(dict(machine_id=m, start=r["scored_at"].iloc[0], end=r["scored_at"].iloc[-1],
                            touches_positive=bool(r["label"].any())))
    return out


def evaluate(scores: pd.DataFrame, truth: pd.DataFrame, threshold: float, horizon_h: float = HORIZON_H,
             step_hours: float | None = None) -> dict:
    df = add_labels(scores, truth, horizon_h)
    df = df[~df["excluded"]].copy()
    df["warn"] = df["score"] >= threshold
    tp = int((df.warn & df.label).sum())
    fp = int((df.warn & ~df.label).sum())
    fn = int((~df.warn & df.label).sum())
    tn = int((~df.warn & ~df.label).sum())
    precision = tp / (tp + fp) if tp + fp else float("nan")
    recall = tp / (tp + fn) if tp + fn else float("nan")
    f1 = 2 * precision * recall / (precision + recall) if tp else (0.0 if tp + fp + fn else float("nan"))

    # ---- events ----
    all_df = scores.copy()
    all_df["scored_at"] = pd.to_datetime(all_df["scored_at"], utc=True)
    leads, per_failure = [], []
    for f in truth.itertuples(index=False):
        w = all_df[(all_df["machine_id"] == f.machine_id) & (all_df["scored_at"] < f.failure_at)
                   & (all_df["scored_at"] >= f.failure_at - pd.Timedelta(hours=horizon_h))
                   & (all_df["score"] >= threshold)]
        early = all_df[(all_df["machine_id"] == f.machine_id) & (all_df["scored_at"] >= f.onset)
                       & (all_df["scored_at"] < f.failure_at - pd.Timedelta(hours=horizon_h))
                       & (all_df["score"] >= threshold)]
        detected = not w.empty
        lead = (f.failure_at - w["scored_at"].min()).total_seconds() / 3600 if detected else float("nan")
        if detected:
            leads.append(lead)
        per_failure.append(dict(failure_id=f.failure_id, machine_id=f.machine_id, category=f.category, gain=f.gain,
                                detected=detected, lead_time_h=lead, early_warning=not early.empty))

    step = pd.Timedelta(hours=step_hours) if step_hours else (
        df["scored_at"].drop_duplicates().sort_values().diff().median() if len(df) else pd.Timedelta(hours=3))
    eps = _episodes(df, step)
    false_eps = [e for e in eps if not e["touches_positive"]]
    machine_days = float(len(df) * (step / pd.Timedelta(days=1))) if len(df) else 0.0

    n_fail = len(truth)
    return dict(
        threshold=threshold, scored_pairs=len(df), positives=int(df.label.sum()),
        tp=tp, fp=fp, fn=fn, tn=tn, precision=precision, recall=recall, f1=f1,
        failures=n_fail, failures_detected=int(sum(p["detected"] for p in per_failure)),
        event_recall=(sum(p["detected"] for p in per_failure) / n_fail) if n_fail else float("nan"),
        median_lead_time_h=float(np.median(leads)) if leads else float("nan"),
        warning_episodes=len(eps), false_episodes=len(false_eps), machine_days=machine_days,
        false_episodes_per_machine_month=(len(false_eps) / machine_days * 30) if machine_days else float("nan"),
        failures_with_early_warning=int(sum(p["early_warning"] for p in per_failure)),
        per_failure=per_failure)


def pool(results: list[dict]) -> dict:
    """Combine several datasets (e.g. several seeds) into one set of metrics by summing counts."""
    tp, fp, fn, tn = (sum(r[k] for r in results) for k in ("tp", "fp", "fn", "tn"))
    precision = tp / (tp + fp) if tp + fp else float("nan")
    recall = tp / (tp + fn) if tp + fn else float("nan")
    f1 = 2 * precision * recall / (precision + recall) if tp else 0.0
    pf = [p for r in results for p in r["per_failure"]]
    leads = [p["lead_time_h"] for p in pf if p["detected"]]
    eps = sum(r["warning_episodes"] for r in results)
    fe = sum(r["false_episodes"] for r in results)
    days = sum(r["machine_days"] for r in results)
    pairs = sum(r["scored_pairs"] for r in results)
    return dict(
        threshold=results[0]["threshold"], datasets=len(results), scored_pairs=pairs,
        positives=sum(r["positives"] for r in results), tp=tp, fp=fp, fn=fn, tn=tn,
        precision=precision, recall=recall, f1=f1, failures=len(pf),
        failures_detected=sum(p["detected"] for p in pf), event_recall=sum(p["detected"] for p in pf) / len(pf),
        median_lead_time_h=float(np.median(leads)) if leads else float("nan"),
        warning_episodes=eps, false_episodes=fe, machine_days=days,
        false_episodes_per_machine_month=(fe / days * 30) if days else float("nan"),
        failures_with_early_warning=sum(p["early_warning"] for p in pf), per_failure=pf)


def by_category(per_failure: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(per_failure)
    if df.empty:
        return pd.DataFrame(columns=["category", "failures", "detected", "median_lead_h"])
    return df.groupby("category").agg(failures=("detected", "size"), detected=("detected", "sum"),
                                      median_lead_h=("lead_time_h", "median")).reset_index()


def by_signal_strength(per_failure: list[dict], cut: float = 0.55) -> pd.DataFrame:
    df = pd.DataFrame(per_failure)
    df = df[df["gain"].notna()]
    if df.empty:
        return pd.DataFrame(columns=["signal", "failures", "detected"])
    df["signal"] = np.where(df["gain"] < cut, "weak (gain<0.55)", "strong (gain>=0.55)")
    return df.groupby("signal").agg(failures=("detected", "size"), detected=("detected", "sum")).reset_index()


def sweep(scores_list: list[pd.DataFrame], truths: list[pd.DataFrame], thresholds) -> pd.DataFrame:
    rows = []
    for th in thresholds:
        r = pool([evaluate(s, t, th) for s, t in zip(scores_list, truths)])
        rows.append({k: r[k] for k in ("threshold", "precision", "recall", "f1", "event_recall",
                                       "median_lead_time_h", "false_episodes", "failures_detected", "failures")})
    return pd.DataFrame(rows)
