# Evaluation of Database: predictive_maintenance_dev

Warning threshold: 30

All data is synthetic. The risk-scoring rules were tuned using different seeds.

## Overall Evaluation Results

- Scored machine-time pairs: 4,144
- Positive pairs (failure within 72 hours): 144
- True positives: 93
- False positives: 28
- False negatives: 51
- True negatives: 3,972
- Precision: 76.9%
- Recall: 64.6%
- F1 score: 70.2%
- Failures detected: 5 out of 6 (83.3%)
- Median warning lead time: 69.9 hours
- Warning episodes: 6
- False warning episodes: 0
- False episodes per machine-month: 0.00
- Failures with an earlier warning more than 72 hours ahead: 3

## Results by Failure Category

- BEARING_WEAR: 1 failure, 1 detected, median lead time 71.5 hours
- ELECTRICAL: 2 failures, 1 detected, median lead time 2.8 hours
- LUBRICATION: 1 failure, 1 detected, median lead time 64.8 hours
- MISALIGNMENT: 1 failure, 1 detected, median lead time 69.9 hours
- OVERHEATING: 1 failure, 1 detected, median lead time 70.2 hours

## How to Interpret These Results

- **Synthetic data only:** The failures were injected by this project's generator, and the rules were designed to recognise patterns such as rising levels, trends and bursts. Real machines are more complex. Validation on real industrial data has not been performed.
- **Limited holdout independence:** Holdout seeds are new random datasets from the same generator and use the same failure mechanisms. They help protect against overfitting the thresholds but do not prove performance on real industrial data.
- **Strict labels:** A warning more than 72 hours before a failure counts as a false positive in precision and recall, even when the machine may genuinely have been degrading. These cases are listed separately as earlier warnings.
- **Lead-time limit:** Warning lead time is capped at 72 hours because the evaluation uses a 72-hour prediction horizon.
- **Correlated observations:** Risk scores are calculated every three hours. Consecutive scoring times are strongly correlated, so precision and recall should not be treated as independent observations.
- **Event recall:** Event recall measures how many actual failure events were detected. It is useful for understanding failure detection, but the small number of failure events means uncertainty remains high.

These results demonstrate performance on controlled synthetic data only. Further validation using real industrial telemetry and maintenance records is required before making real-world performance claims.