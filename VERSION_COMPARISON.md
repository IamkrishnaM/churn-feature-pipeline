# Version Comparison Report

Comparison of versioned features registered in the feature store, 
per the versioning table in feature_spec.md.

## Transaction Count — window 90d vs 30d

_txn_count_last_90d (v1, window_days=90) vs txn_count_last_30d (v1, window_days=30)_

**txn_count_last_90d v1 → txn_count_last_30d v1**

- **Total customers**: 1500
- **Customers with changed values**: 767 (51.1%)

### Distribution (v1)
- Mean: 1.5080
- Median: 1.0000
- Std:  1.5559
- Min:  0.0000
- Max:  9.0000

### Distribution (v2)
- Mean: 0.5553
- Median: 0.0000
- Std:  0.8112
- Min:  0.0000
- Max:  5.0000

### Rank-Order Change
- Spearman (rank) correlation: 0.6854
- Mean absolute rank-percentile change: 17.50

### Interpretation
A substantial fraction of customers changed values. A model consuming this feature would likely produce materially different predictions for many customers between versions.

## Adjusted Spend — window 90d vs 30d

_recent_spend_adjusted_90d (v1, window_days=90, multiplier=0.5) vs recent_spend_adjusted_30d (v1, window_days=30, multiplier=0.5)_

**recent_spend_adjusted_90d v1 → recent_spend_adjusted_30d v1**

- **Total customers**: 1500
- **Customers with changed values**: 770 (51.3%)

### Distribution (v1)
- Mean: 66.7933
- Median: 32.0150
- Std:  85.4240
- Min:  -84.6200
- Max:  585.1936

### Distribution (v2)
- Mean: 25.3697
- Median: 0.0000
- Std:  51.4450
- Min:  -84.6550
- Max:  594.4792

### Rank-Order Change
- Spearman (rank) correlation: 0.6260
- Mean absolute rank-percentile change: 18.63

### Interpretation
A substantial fraction of customers changed values. A model consuming this feature would likely produce materially different predictions for many customers between versions.

## Adjusted Spend — penalty multiplier 0.5 vs 0.75

_recent_spend_adjusted_90d v1 (multiplier=0.5) vs recent_spend_adjusted_90d v2 (multiplier=0.75), same window_

**recent_spend_adjusted_90d v1 → recent_spend_adjusted_90d v2**

- **Total customers**: 1500
- **Customers with changed values**: 111 (7.4%)

### Distribution (v1)
- Mean: 66.7933
- Median: 32.0150
- Std:  85.4240
- Min:  -84.6200
- Max:  585.1936

### Distribution (v2)
- Mean: 65.9106
- Median: 30.3750
- Std:  85.6964
- Min:  -126.9300
- Max:  585.1936

### Rank-Order Change
- Spearman (rank) correlation: 0.9911
- Mean absolute rank-percentile change: 0.94

- Customers crossing quartile boundaries: 30 (2.0%)

### Interpretation
A moderate fraction of customers changed values. The downstream model would likely notice this shift for those customers, but the overall feature distribution is similar.
