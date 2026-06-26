# Daily Learning — 2026-06-26

**Thread:** Product wants auto-block at ninety percent confidence, but holdout accuracy cannot prove scores are honest — tonight we separate routing scores, bin calibration, and folder spam rate so Marcus knows which memo to sign.

**Arc:** spam-filter-bayes · Day 1 · Bayesian Inference + Logistic Regression bridge  
**Pressure:** inv-calibration — bin-averaged scores must match observed spam fractions before the 0.9 gate ships  
**Time:** ~73 min total (2 core + 1 stretch)

## Tonight's lessons

| # | Lesson | Time | Tag |
|---|--------|------|-----|
| 1 | [Why can't Marcus sign off on auto-quarantine from holdout accuracy alone?](/reports/2026-06-26/lesson-01.html) | ~32 min | [core] |
| 2 | [Can Marcus sign an updated folder spam rate tonight without retraining word weights?](/reports/2026-06-26/lesson-02.html) | ~26 min | [core] |
| 3 | [Which audit clause does Product need — folder rate or routing score?](/reports/2026-06-26/lesson-03.html) | ~15 min | [stretch] |

## Checklist

- [ ] **Lesson 1 [core]:** Walk score → bin → count → compare; explain why 91.5% holdout accuracy fails the 0.9 routing memo and what the 0.94 vs 71% high-bin gap proves
- [ ] **Lesson 2 [core]:** Name prior, likelihood, and posterior as folder-belief language on 148/200 → 149/51 without retraining TF-IDF weights
- [ ] **Lesson 3 [stretch]:** Route Product's 0.9 gate, Marcus's folder spam rate memo, and dev accuracy to the correct audit clause on the same 200 emails

## Carry forward

When Product insists on shipping auto-quarantine this week, does Platt or isotonic remap restore bin honesty — and what holdout discipline prevents leakage?
