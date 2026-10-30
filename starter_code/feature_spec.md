# feature_spec.md — Churn Feature Pipeline

<<LEARNER: fill in the SKELETON section below yourself, against skill.md's Domain Context
section and Stage 0's generated data_dictionary.md/feature proposal — correct that proposal,
don't restate it. Do this before opening Claude Code for the build stage. See the EXAMPLE
section below (and Helper Guide.docx) for what a filled-in answer looks like — the example
uses return_rate_90d, which is NOT one of this dataset's real candidate features, so it can't
be copied in as your own answer. Delete the EXAMPLE section and every bracketed prompt in the
SKELETON before you submit.>>

---

## EXAMPLE — reference only, delete before submitting

**Candidate features**
- Feature: return_rate_90d — Source: data/transactions.db — Computation: count(is_returned=1)
  / count(*), trailing 90 days — Zero-activity default: 0.0
- Source justification: row-level needed — 90-day window precision beats the ETL-lagged
  monthly aggregate
- Rationale: predicts churn because a rising return share signals unmet expectations,
  distinct from just low spend — a customer can spend normally and still be trending toward
  churn

**Train/score parity design**
- Shared function/code path: build_features(as_of, source_paths=None, customer_ids=None)
- Only allowed difference: which customer_ids are selected at the end
- as_of: always a parameter, never hardcoded

**Feature store, versioning & lineage**
- Versioned: recent_spend_adjusted (param: repeat_purchase_multiplier, v1=2.0, v2=2.25 —
  recalibrated after v1 understated repeat-purchase value vs. observed return-customer
  distribution), txn_count_recent (param: window_days, v1=90, v2=30)
- Version bump = real param/source/computation change, not a renamed column
- Lineage must reconstruct: source → transform → rationale → parquet_path

**Multi-source judgment calls**
- Feature: return_rate_90d — Source: transactions.db — Why: 90-day window needs precision
  the ETL-lagged aggregate can't guarantee

**Data-quality checks**
- No unexpected nulls after defaulting → catches a transform silently dropping a customer →
  raise / non-zero exit
- Zero-activity customers get 0.0, not null → catches a reindex bug for the 81
  zero-transaction customers → raise / non-zero exit
- return_rate_90d in [0,1]; recent_spend_adjusted ≥ 0 and < $10,000 → catches a unit error or
  duplicate-row join → raise / non-zero exit
- Row count matches customer count (training) or requested customer_ids (scoring) → catches a
  join dropping/duplicating customers → raise / non-zero exit

---

## SKELETON — fill this in

## Candidate features

<<One block per feature — add/remove freely. At minimum per feature, per skill.md's Domain
Context: name, source(s), computation, an explicit zero-activity default (never null/NaN),
and a rationale naming a specific customer behavior distinct from a plausible confound.>>
- **Feature**: <<name>>
- **Source**: <<file/table>>
- **Computation**: <<one line>>
- **Zero-activity default**: <<exact value>>
- **If multiple sources could supply this, which and why?**: <<one phrase>>
- **Rationale**: "This predicts churn because customers who ___ tend to ___, distinct from
  just low spend/frequency because ___."

## Train/score parity design

<<At minimum, per skill.md's Domain Context: the one shared function/code path, the single
allowed difference between training and scoring calls, and how as_of is threaded as a
parameter.>>
- **Shared function/code path**: <<name it>>
- **Only allowed training/scoring difference**: <<one phrase>>
- **How as_of is threaded (not hardcoded)**: <<one phrase>>

## Feature store, versioning & lineage

<<At minimum, per skill.md's Domain Context: which ≥2 distinct features are versioned (each
with ≥2 versions — this floor is fixed), per feature the parameter varied and its value at
each version, the business reason each version differs from the last, and what a lineage
entry must let someone reconstruct without reading code.>>
- **Features versioned**: <<list>>
- Per versioned feature: **Feature** / **Parameter** / **Value per version** / **Reason each
  version differs**: <<fill per feature>>
- **What forces a version bump vs. not**: <<one phrase>>
- **What a lineage entry must let someone reconstruct**: <<one phrase>>

## Multi-source judgment calls

<<At minimum, per skill.md's Domain Context: per feature that could come from either source,
which was chosen and why.>>
- **Feature**: <<name>> — **Source chosen**: <<transactions.db or
  transactions_monthly_agg.parquet>> — **Why**: <<one phrase>>

## Data-quality checks

<<At minimum, per skill.md's Domain Context: no unexpected nulls after defaulting, the
zero-activity default is actually applied, monetary/aggregate features stay within a sane
bound, and row counts reconcile against the customer count. Per check:>>
- **Check**: <<one phrase>> — **Catches**: <<one phrase, tied to this dataset>> —
  **On failure**: <<e.g. raise / non-zero exit>>
