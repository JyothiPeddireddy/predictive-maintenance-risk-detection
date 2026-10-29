# Risk engine evaluation (synthetic data)

Warning threshold: **30** (score 0-100). Horizon: 72 h. All data is SYNTHETIC, produced by this project's own generator.

## Tuning seeds (used to choose the rules and threshold; optimistic)
Seeds: 20261028, 20261029, 20261030, 20261031, 20261032

| Measure | Value |
|---|---|
| Scored (machine, time) pairs | 20746 |
| Positive pairs (failure within 72 h) | 720 |
| Confusion: TP / FP / FN / TN | 447 / 105 / 273 / 19921 |
| Precision | 81.0% |
| Recall | 62.1% |
| F1 | 70.3% |
| Failures detected (event recall) | 27 of 30 (90.0%) |
| Median warning lead time (h, max 72) | 64.8 |
| Warning episodes / false episodes | 38 / 4 |
| False episodes per machine-month | 0.05 |
| Failures that also had an EARLIER warning (>72 h ahead) | 11 |

By failure category:

| category | failures | detected | median_lead_h |
|---|---|---|---|
| BEARING_WEAR | 5 | 5 | 71.2 |
| ELECTRICAL | 7 | 5 | 9.2 |
| LUBRICATION | 5 | 4 | 65.0 |
| MISALIGNMENT | 6 | 6 | 70.0 |
| OVERHEATING | 7 | 7 | 46.8 |

By injected signal strength:

| signal | failures | detected |
|---|---|---|
| strong (gain>=0.55) | 20 | 19 |
| weak (gain<0.55) | 10 | 8 |

Per seed:

| seed | precision | recall | f1 | failures | failures_detected | median_lead_time_h | false_episodes |
|---|---|---|---|---|---|---|---|
| 20261028 | 0.769 | 0.646 | 0.702 | 6 | 5 | 69.933 | 0 |
| 20261029 | 0.879 | 0.653 | 0.749 | 6 | 6 | 63.0 | 0 |
| 20261030 | 0.712 | 0.514 | 0.597 | 6 | 4 | 60.958 | 1 |
| 20261031 | 0.966 | 0.59 | 0.733 | 6 | 6 | 50.475 | 1 |
| 20261032 | 0.765 | 0.701 | 0.732 | 6 | 6 | 70.258 | 2 |

## Holdout seeds (never used for tuning; the honest test)
Seeds: 7000001, 7000002, 7000003, 7000004, 7000005, 7000006, 7000007, 7000008, 7000009, 7000010

| Measure | Value |
|---|---|
| Scored (machine, time) pairs | 41481 |
| Positive pairs (failure within 72 h) | 1440 |
| Confusion: TP / FP / FN / TN | 975 / 276 / 465 / 39765 |
| Precision | 77.9% |
| Recall | 67.7% |
| F1 | 72.5% |
| Failures detected (event recall) | 56 of 60 (93.3%) |
| Median warning lead time (h, max 72) | 69.4 |
| Warning episodes / false episodes | 73 / 9 |
| False episodes per machine-month | 0.05 |
| Failures that also had an EARLIER warning (>72 h ahead) | 28 |

By failure category:

| category | failures | detected | median_lead_h |
|---|---|---|---|
| BEARING_WEAR | 14 | 14 | 70.6 |
| ELECTRICAL | 13 | 10 | 13.2 |
| LUBRICATION | 11 | 10 | 69.7 |
| MISALIGNMENT | 10 | 10 | 69.9 |
| OVERHEATING | 12 | 12 | 58.0 |

By injected signal strength:

| signal | failures | detected |
|---|---|---|
| strong (gain>=0.55) | 40 | 40 |
| weak (gain<0.55) | 20 | 16 |

Per seed:

| seed | precision | recall | f1 | failures | failures_detected | median_lead_time_h | false_episodes |
|---|---|---|---|---|---|---|---|
| 7000001 | 0.727 | 0.778 | 0.752 | 6 | 6 | 69.392 | 2 |
| 7000002 | 0.8 | 0.722 | 0.759 | 6 | 6 | 67.542 | 3 |
| 7000003 | 0.722 | 0.847 | 0.78 | 6 | 6 | 69.75 | 3 |
| 7000004 | 0.818 | 0.625 | 0.709 | 6 | 5 | 66.4 | 0 |
| 7000005 | 0.711 | 0.562 | 0.628 | 6 | 6 | 40.167 | 0 |
| 7000006 | 0.851 | 0.674 | 0.752 | 6 | 5 | 70.567 | 0 |
| 7000007 | 0.849 | 0.625 | 0.72 | 6 | 6 | 46.492 | 0 |
| 7000008 | 0.881 | 0.618 | 0.727 | 6 | 5 | 58.3 | 0 |
| 7000009 | 0.728 | 0.764 | 0.746 | 6 | 6 | 69.917 | 1 |
| 7000010 | 0.784 | 0.556 | 0.65 | 6 | 5 | 70.033 | 0 |

## How to read these numbers (limits)
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
