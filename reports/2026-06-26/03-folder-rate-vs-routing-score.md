# [Logistic Regression] Which audit clause does Product need — folder rate or routing score?

**Time**: ~15 min | **Topic**: Logistic Regression | **Pressure**: Product reads Q-041's predict_proba while Marcus signs a folder spam rate memo — why aren't those interchangeable on the same 200 emails?

## Scene card

Corporate email product. **200 labeled quarantine emails**: **149 spam, 51 ham** after last night's tag (**74.5% folder spam rate**). **Priya** maintains ridge **logistic regression** on **TF-IDF** word scores (~10,000 sparse features per message — not embeddings). **Marcus** (Legal) signs **folder composition** memos. **Product** ships **auto-quarantine** when **`predict_proba` ≥ 0.9**.

**Q-041** still scores **0.94** until retrain. Holdout **accuracy** remains **91.5%** at argmax **0.5**. The **high bin** still shows **~0.94 claimed vs ~71% observed** — scores are overconfident for routing.

Tonight Leadership asks you to **pick tools**, not re-derive every table: **which number goes with which decision?**

## Story so far

- **Lesson 1:** Holdout accuracy cannot certify the **0.9** gate; **reliability bins** audit per-email score honesty — high bin fails (**0.94 vs ~71%**).

- **Lesson 2:** **Folder spam rate** updates on human labels (**148/52 → 149/51**) via **prior + tag → posterior**, **without** retraining TF-IDF weights.

- **Same 200 rows, three memo objects** — Leadership keeps collapsing them into one dashboard tile.

## Terms tonight

- **Estimand**: The exact quantity a memo certifies — write it in English before signing.

- **Routing score (`predict_proba`)**: Per-email spam probability from logistic weights — input to Product's **≥ 0.9** rule.

- **Folder spam rate**: Fraction of spam if you random-draw from the quarantine folder — Marcus's **composition** memo (**149/200**).

- **inv-calibration (pressure invariant)**: Under auto-quarantine pressure, **scores must be bin-honest** — claimed probabilities must match observed spam fractions in score bins.

- **Tool routing**: Matching each business question to the correct statistical object and diagnostic — not whichever number looks largest.

## The situation

Wednesday exec pre-read stacks two bullets:

1. Marcus signed **folder rate ≈ 74.5%** with a credible band on **149/200**.  
2. Product wants **Q-041 @ 0.94** auto-quarantined before the afternoon deploy.

The VP asks: "Both numbers are about spam on the same **200 emails** — why two memos?"

Because **Product's clause** and **Marcus's clause** are **different questions**. Collapsing them ships the wrong proof to the wrong gate.

## Why the obvious approach breaks

**Obvious merge — "Folder is 74.5% spam, so 0.94 is fine."**
**74.5%** is **batch composition**. **0.94** is **this email's modeled score**. A folder can be three-quarters spam while a **high-bin score still overstates** per-row probabilities (**71% observed vs 0.94 claimed**). Composition does not certify routing honesty.

**Obvious merge — "91.5% accuracy backs 0.94."**
Already rejected: accuracy is argmax at **0.5**, not calibration at **0.9** (H-144/H-146 in one line).

**Obvious merge — "Marcus's posterior fixes Product's gate."**
Updating folder rate from **+1 label** does **not** remap **predict_proba** bins. Different tool chain.

## Building the mechanism — three-row audit table

Under **inv-calibration** pressure, route questions to tools:

```
  QUESTION                          ESTIMAND           TOOL TONIGHT        SIGNER
  ────────────────────────────────────────────────────────────────────────────────
  "Auto-block at score ≥ 0.9?"      Bin-honest         Reliability bins    You → Product
                                    per-email scores   (0.94 vs 71% FAIL)

  "How spammy is the folder?"       Folder rate        Beta count update   Marcus
                                    149/200            prior+tag→posterior

  "Does model pick labels well?"    Argmax accuracy    Holdout @ 0.5       Priya (dev)
                                    91.5%              NOT routing memo
```

Same **200 labeled emails**. Three **non-interchangeable** outputs.

## Same problem, different lens

**Lens A — Logistic regression as ranker:** TF-IDF + ridge logistic separates spammy word patterns; **91.5%** says ranking works at **0.5**.

**Lens B — Logistic regression as probability machine:** Product treats **`predict_proba`** literally at **0.9**. Bin audit says **Lens B fails** in the top bin even while **Lens A** looks fine.

**Lens C — Folder composition:** Marcus's folder memo ignores word weights; counts labeled rows only.

Identical data. **Different estimands.** Tool-switch rule: **name the clause first**, then open the spreadsheet column that matches.

ASCII decision fork for Q-041 deploy:

```
                    Q-041 deploy?
                         |
            ┌────────────┴────────────┐
            │                         │
     Product clause              Marcus clause
     "score ≥ 0.9 safe?"         "folder rate band OK?"
            │                         │
     Check high bin               Check 149/200
     0.94 vs 71% FAIL            posterior band OK
            │                         │
     BLOCK auto-quarantine        Does NOT unblock
     until remap/threshold        Product gate by itself
```

## Which tool would you deploy?

**Product constraint:** Ship auto-quarantine this week if legally defensible.

**Legal constraint:** No routing on uncertified probability claims.

**Deploy recommendation tonight:**

| Action | Tool | Why |
|--------|------|-----|
| **Do not** enable **0.9** auto-quarantine on raw scores | Bin calibration audit | High bin overconfidence |
| **Do** keep human review on **Q-041** | Per-email score + bin context | **0.94** unreadable without remap |
| **Do** accept Marcus's folder memo on **149/200** | Beta ledger update | Composition unknown answered |
| **Defer** Platt/isotonic remap | Logistic post-processing | Mechanics queued — not tonight |
| **Use** holdout accuracy internally | Dev metric @ 0.5 | Not Legal's routing object |

One sentence carry-forward: **Ridge logistic owns ranking and raw scores; bin audit owns whether 0.9 is shippable; Beta ledger owns folder rate — never swap columns in the exec deck.**

## Graph checkpoint

**Pressure invariant tonight:** inv-calibration — bin-averaged scores must match observed spam fractions before the **0.9** gate ships.

**Connected topics on the graph:**
- **E-calibration-hub** — calibration sits between **raw logistic scores** and **Product routing**
- **E-109** — folder spam rate is a **separate estimand** from per-email **predict_proba**
- **E-110** — holdout **accuracy** certifies argmax labels, not threshold honesty
- **E-111** — interval language (**credible** vs **Wilson**) attaches to **folder memos**, not score bins

**Tool-switch rule:** Read the **audit clause** aloud first — "routing," "composition," or "dev quality" — then open the tool that matches. If the clause says **≥ 0.9**, open **bins**; if it says **folder rate**, open **count ledger**; if it says **model iteration**, open **accuracy @ 0.5** — never the wrong column because the number looks comforting.

## Worked routing scenario — two emails, one policy

Same afternoon deploy meeting:

| Row   | predict_proba | True label | Folder rate relevant? | Bin audit relevant? |
|-------|---------------|------------|----------------------|---------------------|
| Q-041 | 0.94          | spam       | No (row score)       | **Yes — high bin overconfident** |
| Q-102 | 0.41          | ham        | No                   | Low bin — not gating |

Product wants to auto-block **Q-041** only. Marcus's **74.5% folder memo** does **not** greenlight that row — wrong estimand. **Bin table** red-flags **Q-041** even though argmax would call it spam correctly.

**Deploy stance:** human review on **Q-041**; accept folder memo for **composition compliance**; keep **91.5% accuracy** in engineering notes only.

## Which tool would you deploy? — constraint checklist

Product constraints from Leadership slide:

- **Ship auto-quarantine this week if legally defensible** → **Blocked** until bin honesty fixed or threshold lowered with documented risk
- **Do not pause human review queue** → **Compatible** — keep reviewers on **≥ 0.9** rows
- **Single dashboard number for execs** → **Reject** — force **three-row table** instead of one hero metric

Tool picks:

1. **Reliability bin audit (logistic regression diagnostic)** — **deploy now** for routing decisions  
2. **Beta count ledger (Bayesian Inference on folder rate)** — **deploy now** for Marcus memos  
3. **Holdout accuracy** — **retain internally**, **exclude from Legal routing packet**  
4. **Platt / isotonic remap** — **queue**, not tonight — mechanics deferred per curriculum  

## Stretch close — say it for the VP

**"The folder being seventy-four point five percent spam does not prove that a zero point nine four score means ninety-four percent — and ninety-one point five percent accuracy does not prove the zero point nine gate is safe. Pick the audit clause, then pick the tool."**

## Traps you would have fallen into

**Trap 1 — Substituting 74.5% for 0.94 in Product's rule.** Wrong estimand; VP memo sounds neat, audit fails.

**Trap 2 — Waiting on folder update to "fix" scores.** Posterior on folder rate never touched TF-IDF weights.

**Trap 3 — Treating stretch bridge as re-proof of Lesson 1 bins.** Reference the gap; don't rebuild the whole reliability walk — diagnose **routing**, not rediscover calibration.

**Trap 4 — "Both emails above 0.9 share the same score, so one audit covers all."** Q-041 at **0.94** and another row at **0.91** share a **bin**, not an identical number — the audit clause is bin-level frequency, not per-row equality.

## Mental model checkpoint

**"Same two hundred emails, three audit clauses: argmax accuracy for dev quality, bin calibration for the zero point nine gate, folder rate for Legal's composition memo — pick the tool that matches the question before signing."**

Self-check:
1. Marcus signed a folder memo — does that unblock Q-041 auto-quarantine? Why not?
2. Which graph edge (E-109, E-110, E-calibration-hub) would you cite for Product's gate?
3. Under this week's Product constraints, name the one tool you **defer** and why.

Open question for tomorrow: **If Product demands a remap, does Platt or isotonic restore bin honesty without hiding leakage — and does that still ignore weight uncertainty?**
