# Evaluation of database `predictive_maintenance_dev`

Threshold 30. SYNTHETIC data; rules were tuned on other seeds.

| Measure | Value |
|---|---|
| Scored (machine, time) pairs | 4144 |
| Positive pairs (failure within 72 h) | 144 |
| Confusion: TP / FP / FN / TN | 93 / 28 / 51 / 3972 |
| Precision | 76.9% |
| Recall | 64.6% |
| F1 | 70.2% |
| Failures detected (event recall) | 5 of 6 (83.3%) |
| Median warning lead time (h, max 72) | 69.9 |
| Warning episodes / false episodes | 6 / 0 |
| False episodes per machine-month | 0.00 |
| Failures that also had an EARLIER warning (>72 h ahead) | 3 |

By failure category:

| category | failures | detected | median_lead_h |
|---|---|---|---|
| BEARING_WEAR | 1 | 1 | 71.5 |
| ELECTRICAL | 2 | 1 | 2.8 |
| LUBRICATION | 1 | 1 | 64.8 |
| MISALIGNMENT | 1 | 1 | 69.9 |
| OVERHEATING | 1 | 1 | 70.2 |

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
