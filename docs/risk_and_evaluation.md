# Risk engine and evaluation (Phase 4)

## What the risk score is
For every machine, at any time `t`, the engine returns a score from 0 (no sign of trouble) to 100 (strong, sustained
signs of degradation). A score of **30 or more raises a warning** (`HIGH`); 15-30 is `MEDIUM`; below 15 is `LOW`.
It is a rule-based score, not machine learning, so every number can be traced to a rule (`src/risk/engine.py`).

| Step | Rule |
|---|---|
| Sensor quality | A sensor is ignored if it is flagged `FAULTY`, drops out (>= 30% missing in 6 h) or flat-lines (identical readings for 4 h+). If two sensors of one type disagree strongly, the high one is ignored. |
| Baseline | The machine's own normal: median and spread of RUNNING readings from 21 days to 3 days ago. Readings during `MAINTENANCE` are ignored. |
| Level | How far the last-24 h median is above the baseline, in baseline spreads. |
| Trend | How fast the last-72 h readings rise (spreads per day), only counted if the level is already elevated. |
| Spikes | Share of last-24 h readings far above baseline, counted only if the spikes are spread over 8-16+ hours (shorter bursts = harmless surge). |
| Combine | Sensor score = strongest signal. Type score = blend of mean and lowest valid sensor. Machine score = best type + 25% of the second type above 20. |
| Maintenance | After a corrective repair the older readings are dropped (status `POST_REPAIR` until a new baseline exists). Preventive maintenance is not treated as a fix. |
| Warm-up | Until a machine has about 2 days of baseline data (>= 3 days after start) the status is `WARMING_UP` and the score is 0. |

## Target-leakage protections
1. The engine's inputs (`src/risk/data.py`) have a fixed list of columns: telemetry, sensor status changes and
   work-order timing. The work-order query leaves out the failure link; `failure_event` is never read.
2. Test: no file in `src/risk/` may mention failure/ground-truth names or import from `src/evaluation`,
   `src/generator` or `src/models`.
3. Test: an extra label column in the inputs is rejected.
4. Point-in-time test: scores at time `t` are identical whether or not data after `t` exists.
5. Ground truth is read only by `src/evaluation/` (and only to judge the scores).

## How it was evaluated
- **Labels:** a (machine, time) pair is positive if that machine fails within the next 72 h. Times while a machine is
  down (until 24 h after repair) are excluded. Scores are computed every 3 h.
- **Measures:** precision, recall, F1, confusion matrix, event recall (failures with a warning in the 72 h before),
  warning lead time (first warning to failure, max 72 h), and false warning episodes.
- **Tuning vs holdout:** the rules and the threshold were chosen using only 5 *tuning* datasets (seeds 20261028-20261032).
  The threshold rule was fixed in advance: the highest threshold that still catches >= 90% of failures on the tuning
  data (30). Then 10 *holdout* datasets (seeds 7000001-7000010), never used for tuning, were scored once.
  (Earlier in development the sensor-agreement blend and score scaling were tried on the tuning seeds only.)

## Results (synthetic data, dev scenario config, threshold 30)
| | Tuning (5 datasets, 30 failures) | Holdout (10 datasets, 60 failures) |
|---|---|---|
| Precision | 81.0% | 77.9% |
| Recall (per scored time) | 62.1% | 67.7% |
| F1 | 70.3% | 72.5% |
| Failures with a warning in the last 72 h | 27 of 30 (90.0%) | 56 of 60 (93.3%) |
| Median warning lead time | 64.8 h | 69.4 h |
| False warning episodes | 4 | 9 (about 0.1 per machine-month) |

Holdout details: strong-signal failures 40 of 40 detected, weak-signal 16 of 20. By category: bearing wear 14/14,
misalignment 10/10, overheating 12/12, lubrication 10/11 (1 missed), **electrical 10/13 with a median lead of only
13 h** (electrical faults appear as late spikes). 28 of the 60 failures also had a warning more than 72 h ahead, which
the strict labels count as false positives.

These numbers are **different from the older figures** quoted in the project brief (precision 1.00, recall 0.521,
F1 0.685, event recall 0.758, lead 37.1 h). That older code is not in this project, so those figures could not be
reproduced and are not used.

## Limits - please read
- **Synthetic data only.** The failures were injected by this project's generator and the rules were written to
  recognise that kind of pattern. Real machines will be messier; real-world performance would very likely be lower.
  No real industrial data has been used.
- **Holdout is only partly independent.** It guards against over-tuning the threshold, not against a mismatch
  between the simulator and reality.
- **Small sample.** 60 failures: a 93% event recall could easily be 85-98% in another sample.
- **Per-time precision/recall** use strongly correlated scoring times; read event recall and false episodes first.
- **Known weaknesses:** electrical faults warned late; weak signals missed; after a repair the machine is blind for
  about 2-3 days (a second failure right after a repair would be missed); only temperature and vibration exist.
- **Not done:** peer-machine comparison, load/shift normalisation, learning from labels, real-data validation.

## Commands (PowerShell; use your dev database, never the original)
```powershell
python -m src.cli --db predictive_maintenance_dev score                 # reports/risk_scores.csv
python -m src.cli --db predictive_maintenance_dev report                # reports/machine_risk_report.csv + maintenance_downtime_summary.csv
python -m src.cli --db predictive_maintenance_dev evaluate              # metrics from the database's own failure records
python -m src.cli evaluate-holdout                                      # tuning vs holdout, in memory, ~1 minute -> reports/evaluation_holdout.md
```
All four are read-only for the database.
