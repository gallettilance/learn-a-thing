# [Bayesian Inference] Why can't Marcus sign off on auto-quarantine from holdout accuracy alone?

**Time**: ~32 min | **Topic**: Bayesian Inference | **Pressure**: Product wants to auto-block mail at score 0.9, but Legal will not accept "91.5% accurate" as proof the threshold is safe

## Scene card

You are the ML engineer on a corporate email product. A legacy keyword filter is being replaced. Leadership cares about *how sure* you are before mail is auto-quarantined — not just whether the model got labels right on a holdout set.

**Priya** trains classifiers overnight. **Marcus** (Legal counsel) signs audit memos. **Product** wants auto-quarantine when the model's spam score hits **0.9 or higher**.

The working batch is a **quarantine folder**: **200 labeled emails** pulled aside for human review. Right now the ledger reads **148 spam** and **52 ham** — a **74% folder spam rate** if you pick a random row.

The classifier is **ridge-regularized logistic regression** on **TF-IDF** features. Each email becomes a sparse vector of about **10,000 word importance scores** (one weight per vocabulary word from term-frequency × inverse-document-frequency — **not** a neural embedding, **not** an SVD compression). Logistic regression learns one coefficient per word plus an intercept, then outputs a per-email **`predict_proba`** spam score between 0 and 1.

Product's rule is blunt: **if predict_proba ≥ 0.9, auto-quarantine without human review.** Marcus's rule is different: he will not sign until someone shows **which number certifies that rule** — and on **which object** (one email? the whole folder? a holdout test?).

Tonight's pressure is on **email Q-041**, a quarantine row Product wants routed automatically. Priya's model gives Q-041 a score of **0.94**. Product reads that as "94% confident — ship it." Marcus reads the same screen and asks a harder question: **does 91.5% holdout accuracy prove that 0.94 means what Product thinks it means?**

## What you already know on this exact problem

Before any new vocabulary, name what is already on the table:

- **148 spam and 52 ham** in a fixed quarantine folder of **200** labeled rows.
- **Ridge logistic regression** on sparse **TF-IDF word scores** — roughly ten thousand numbers per email feeding one weight vector.
- **`predict_proba`** — one spam score per email from those weights through a sigmoid.
- **91.5% holdout accuracy** — on a held-out test slice, the model's argmax label at **0.5** matches human labels that often.
- **Product's gate** — auto-quarantine when a single row's score is **≥ 0.9**, not when argmax at 0.5 says spam.

You are **not** retraining weights tonight. You are asking whether an existing dashboard number (**91.5%**) can sign Product's **0.9** policy. That is a different question from "is the folder mostly spam?" — we preview that separation so you do not swap columns; the folder-rate memo earns its own lesson next.

## Same numbers, two philosophies (preview only)

On identical rows, people read the same spreadsheet with different goals:

| Lens | What it optimizes tonight | Example number on anchor |
|------|---------------------------|--------------------------|
| **Ranking / label pick** | Did we pick spam vs ham at cutoff 0.5? | **91.5%** holdout accuracy |
| **Per-email probability claim** | Among emails scored near 0.9, does claimed spam rate match observed spam rate? | High bin **~0.94 claimed vs ~71% observed** |
| **Folder composition** (preview) | If you random-draw from the folder, what fraction is spam? | **148/200 = 74%** — wrong memo for routing |

Tonight you earn the **middle row** — bin honesty for Product's gate. The third row is Marcus's parallel track; do not substitute **74%** for **0.94** in Product's rule.

## Terms tonight

- **Quarantine folder**: A holding bin of emails set aside for review before Product auto-blocks or releases them. Tonight's labeled sample is 200 rows from that folder.

- **Holdout accuracy**: The fraction of emails in a held-out test set where the model's predicted label (spam or ham) matches the human label. Priya's ridge logistic scores **91.5%** on holdout — correct argmax labels, not a statement about score honesty at 0.9.

- **`predict_proba`**: The model's per-email spam probability score in (0, 1), computed from TF-IDF word weights through the logistic sigmoid. **One number for one email** — not the folder's overall spam fraction.

- **Auto-quarantine threshold**: Product's routing rule — any email with `predict_proba` ≥ **0.9** gets blocked without human review.

- **Calibration (bin honesty)**: Within groups of emails that received similar scores, the **average claimed probability** should match the **observed spam fraction**. If emails scored near 0.9 are only spam **71%** of the time, the scores are **overconfident** in that bin.

- **Reliability diagram**: An audit chart that sorts emails by score into bins, compares **mean predicted spam rate** in each bin to **observed spam rate**, and shows whether the model's probability claims match reality.

- **Folder spam rate**: If you randomly draw one email from the quarantine folder, what fraction are actually spam? On 148 of 200 labels that rate is **74%**. This is a **composition** question about the folder — not the same object as Q-041's single-row score.

## The situation

Monday standup ends with Product waving a dashboard: "We're at **91.5% holdout accuracy**. Turn on auto-quarantine at **0.9** tonight."

Marcus replies from the audit channel: "Accuracy on which emails, measured how, and what does that prove about **0.9** specifically?"

You pull up the same 200-row quarantine ledger everyone has been staring at: **148 spam, 52 ham, total 200**. Priya's ridge logistic was trained with TF-IDF word features — roughly ten thousand sparse scores per message feeding one weight vector. The model ranks mail well enough that **91.5%** of holdout rows get the right spam/ham label when you round the score at 0.5.

Product hears "91.5%" and maps it to "the model is right more than nine times out of ten, so a **0.94** on Q-041 is basically certain."

Marcus hears "91.5%" and maps it to "you counted argmax hits on a test split — **show me the clause** that connects that percentage to **threshold routing at 0.9**."

Those are not the same reading. And until someone names the difference, Leadership will keep treating one dashboard tile as proof for three different decisions.

Marcus sends the question Product keeps dodging — paste this into your notes:

> **Clause A:** Does **91.5% holdout accuracy** certify that **`predict_proba` ≥ 0.9** is safe for auto-quarantine?  
> **Clause B:** Does **Q-041's 0.94** mean "roughly ninety-four percent of similar emails are spam"?  
> **Clause C:** Does **148/200 folder spam rate** substitute for either A or B?

Your job tonight: answer **A** and **B** with the bin mechanism; preview **C** as **wrong column for routing**; defer **C's proper memo** to lesson two. If Leadership cannot state which clause they need signed, stop the meeting — **estimand first, spreadsheet second**.

## What Priya, Product, and Marcus each need

Three people stare at the same screen and want **different proof objects**:

| Person | Job tonight | What they are asking for | Wrong substitute |
|--------|-------------|--------------------------|------------------|
| **Priya** (ML engineer) | Ship a model that ranks spam well and outputs scores | "Did holdout labels match at 0.5?" → **91.5% accuracy** | Using accuracy to certify the **0.9** gate |
| **Product** | Auto-block high-score mail this week | "When score ≥ 0.9, is spam frequency near 90%+?" → **bin calibration** | Treating **0.94** on one row as self-evident |
| **Marcus** (Legal) | Sign the routing memo | "Show me repeatable counts that **0.9 scores mean what English claims**" → **reliability bins** | Signing on **91.5%** or **74% folder rate** instead |

**How Priya gets what Product actually needs:** not another accuracy sprint — a **holdout export** with frozen `predict_proba`, sorted into bins, with spam counts compared to mean claimed score. Priya already has the scores; the missing step is the **audit spreadsheet**, not a retrain.

**Where Q-041's 0.94 comes from (one trace, no detour):** words in Q-041 → sparse TF-IDF vector → dot product with Priya's learned coefficients → sigmoid → **0.94**. That number is **frozen until retrain**. It is **not** copied from another quarantine row. **Q-088** on the same folder might score **0.41** — same pipeline, different words, different score. Two emails Product wants quarantined do **not** automatically share a score; only the **≥ 0.9 rule** groups them for policy.

**What "94% on this email" would mean if calibrated:** among many holdout emails whose scores land in the **same high bin** as Q-041, roughly **94%** should actually be spam. That is a **frequency claim about a group of similarly scored emails** — not "this one email has a 94% property." The high bin shows **~71% observed** against **~0.94 claimed** — so the English sentence Product wants is **not licensed** by the data.

## Why the obvious approach breaks

The obvious fix is to cite **holdout accuracy** in the memo Product wants signed. It is a real number (**91.5%**), it comes from a disciplined train/holdout split, and it sounds like "the model works."

Here is why Marcus is right to reject it for the **0.9 auto-quarantine** clause.

**Holdout accuracy answers a label-matching question.** Take each holdout email, compare the model's predicted class (spam if score > 0.5, ham otherwise) to the human label, count hits. **91.5%** means the argmax label is correct on that metric. It does **not** ask: "Among emails the model scored **0.90–0.95**, what fraction were actually spam?"

**Product's rule uses a score threshold, not argmax at 0.5.** Auto-quarantine fires on **predict_proba ≥ 0.9**. A model can be **91.5% accurate** at 0.5 while systematically **overstating** probabilities in the high bin — claiming ~0.94 when reality is closer to 0.71. Accuracy at 0.5 never audits that failure mode.

Concrete intuition on Q-041: Product reads **0.94** as "94% chance this specific email is spam." Holdout accuracy never tested that sentence. It tested "did we pick the right side of 0.5?" — a cheaper claim.

Marcus's memo objection, in one line: **holdout accuracy is the wrong memo object for a threshold routing rule.** It certifies ranking-ish label picks, not **probability honesty at 0.9**.

```
  WHAT PRODUCT NEEDS SIGNED          WHAT 91.5% HOLDOUT ACTUALLY IS
  ─────────────────────────          ───────────────────────────────
  "Scores ≥ 0.9 mean ~90%+ spam"     "Argmax at 0.5 matches labels"
  Per-threshold calibration          Global label hit rate
  Bin-level frequency audit            One number, one cutoff (0.5)
```

We are **not** opening the folder spam-rate update path tonight — that is the next lesson's pressure. Tonight we earn **why Product's favorite metric fails** and **what audit object replaces it** for per-email scores.

## Building the mechanism — what Q-041's score actually is

Before we can audit **0.94**, we need to say where that number lives — without confusing it with folder composition.

**Step 1 — Fix the estimand in English.** Q-041's **0.94** is a **per-email claim**: given this message's TF-IDF word vector, the fitted logistic weights produce a spam probability for **this row only**. It is **not** "74% of the folder is spam." It is **not** holdout accuracy. It is **one routing input** for Product's gate.

**Step 2 — Trace the pipeline (one line on TF-IDF, no detour).** Words in Q-041 become sparse TF-IDF scores → dot product with Priya's learned coefficients → sigmoid → **0.94**. Retraining changes weights; **tonight we are not retraining** — we are asking whether **0.94 means what English suggests**.

**Step 3 — Separate three objects Leadership keeps stacking:**

| Memo object | Question it answers | On Q-041 / 200 rows |
|-------------|---------------------|---------------------|
| Holdout accuracy | Did argmax labels match? | **91.5%** — wrong gate for 0.9 |
| `predict_proba` | What score does this email get? | **0.94** on Q-041 — a **claim**, not yet audited |
| Folder spam rate | What fraction of the folder is spam? | **148/200 = 74%** — composition, not per-row routing |

The middle row is tonight's path: **predict_proba is a per-email claim that must be checked for bin honesty** — not assumed from accuracy.

If Product treats **0.94** like a calibrated probability without evidence, they are smuggling a **frequency statement** ("94% of cases like this are spam") from a **score** that was never audited at that level. Marcus's job is to block that smuggle.

## Building the mechanism — the six-step audit recipe

Product will not accept vibes. They need a **repeatable audit** anyone can re-run on the same labeled emails. Walk this recipe once on Priya's holdout export — same modeling family, same TF-IDF pipeline, **no retrain**:

**Step 1 — Name the decision.** Auto-quarantine at **≥ 0.9**, not "be accurate at 0.5."

**Step 2 — Export frozen scores.** Every holdout row: human label + `predict_proba` from the current ridge logistic model.

**Step 3 — Sort** rows by score from low to high.

**Step 4 — Bin** into buckets (deciles 0.0–0.1, …, 0.9–1.0, or four bins of ten for teaching).

**Step 5 — Count inside each bin:**
   - **Mean claimed spam rate** = average `predict_proba` in the bin
   - **Observed spam fraction** = (# actually spam) / (# emails in bin)

**Step 6 — Compare.** Honest calibration hugs the diagonal: claimed ≈ observed. Overconfidence shows **claimed above observed** in the bin where Product lives.

That is the whole mechanism — **score → bin → count → compare**. Tomorrow's articles ask which assumptions behind this recipe might break; tonight you execute it once until the steps feel automatic.

## Building the mechanism — from score to bin to count to observed rate

Walk the recipe on the holdout slice Priya already scored:

**Read the high bin where Q-041 lives.** Emails with scores **≥ 0.9** land in the top bin. Priya's spreadsheet shows:
   - **25 emails** in that bin (small but not empty)
   - **Mean claimed score ≈ 0.94**
   - **Observed spam: 18 of 25 = 72%** (round to **71%** in the memo)

That gap — **0.94 claimed vs ~71% observed** — is not a rounding error. It is **mechanism**: the model **ranks** well enough for 91.5% argmax accuracy, but **probability claims in the top bin are overstated**. Product's auto-quarantine rule reads those overstated claims literally.

ASCII sketch of the audit (diagonal = honest):

```
  Observed spam fraction
  1.0 |                              ·  honest
      |                         ·
  0.9 |                    ·
      |               ·
  0.7 |                          ×  HIGH BIN GAP
      |                     (claimed 0.94,
  0.5 |          ·               observed 0.71)
      |     ·
  0.0 |_____|_____|_____|_____|_____|_____
           0.5        0.7    0.9        1.0
                Mean predict_proba in bin
```

**Decide.** Marcus can now write a sentence Legal understands: "We **cannot** certify that `predict_proba ≥ 0.9` implies ~90%+ spam frequency, because in the holdout high bin mean claim **0.94** coexists with observed **71%**. Holdout accuracy **91.5%** does not contradict this — it was never measuring bin honesty."

## Building the mechanism — a worked bin table (holdout slice)

Picture Priya's holdout export — **40 labeled emails** held out from training, each with a human spam/ham tag and a frozen `predict_proba`. Sort the 40 rows by score. Split into **four bins of ten**:

```
  Bin (score range)   n   Mean predict_proba   Spam count   Observed spam %
  ─────────────────────────────────────────────────────────────────────────
  0.00 – 0.25          10        0.12              1            10%
  0.25 – 0.50          10        0.38              3            30%
  0.50 – 0.75          10        0.61              6            60%
  0.75 – 1.00          10        0.91              7            70%
```

Read row by row — **one mechanism move per row**:

**Low bin (0.12 claimed, 10% observed):** Scores slightly **underconfident** — nobody proposes auto-quarantine at 0.12 anyway.

**Mid bins (0.38 vs 30%, 0.61 vs 60%):** Rough alignment — compatible with **91.5% argmax accuracy** at 0.5 on the full holdout.

**High bin (0.91 mean claim, 70% observed):** Product's neighborhood. Q-041's **0.94** sits here. Only **7 of 10** are spam — **70%**, not **91%**. Scale to the full high tail (**25 emails ≥ 0.9**, mean **0.94**, **18/25 = 72%**) and the story stays: **overconfidence at the routing threshold**.

Honest models hug the **45° line** on a reliability plot. Our high bin sits **below** the line — the model **claims more spam probability than frequency justifies**.

## Building the mechanism — same argmax, different routing risk

Two holdout emails illustrate why **accuracy ≠ threshold safety**:

| Email | predict_proba | True label | Argmax @ 0.5 | Hits 0.9 gate? |
|-------|---------------|------------|--------------|----------------|
| R-12  | 0.52          | spam       | Correct      | No             |
| R-88  | 0.96          | spam       | Correct      | **Yes**        |
| R-91  | 0.93          | ham        | Wrong        | **Yes**        |

**91.5% accuracy** averages argmax hits — mostly forgiving mid-scores like R-12. **Auto-quarantine** only sees rows like R-88 and R-91. If the high bin observes **71% spam** but claims **94%**, then **R-91-type errors** — ham mail above 0.9 — are **more frequent than the score language implies**. Product's policy magnifies **calibration failure** in a thin tail accuracy never stress-tests.

Marcus's question is therefore precise: **does the error rate among scores above 0.9 match the probability printed next to each score?** Holdout accuracy never asks that conditional question.

## Why folder spam rate is a different column (preview only)

Leadership will try **148/200 = 74%** as a comfort number. Good for **composition audits** — Marcus cares about that on a different memo track. It does **not** answer Q-041's row-level claim. A folder can be **74% spam overall** while **high-scoring emails are still overconfident** — both statements true simultaneously on the same 200 rows.

We preview the separation so you do not collapse columns tonight; the **folder-rate update path** earns its own lesson next.

## Guided reconstruction — rebuild the audit yourself

Close your laptop metaphorically and replay the chain:

1. **Name the decision** — auto-quarantine at **≥ 0.9**, not "be accurate."
2. **Reject the wrong proof** — **91.5%** is argmax at **0.5**.
3. **Name the score's job** — **predict_proba** is a **per-email** claim from TF-IDF logistic weights.
4. **Sort and bin** holdout scores.
5. **Count spam in the high bin** — **18/25**, not **94%**.
6. **Compare claim vs observed** — **0.94 vs 71%** gap.
7. **Block the routing memo** until remap, threshold change, or human review — diagnosis complete.

If any step blurs, re-read **Terms tonight** — the vocabulary is doing legal work.

## Anticipated confusion — dialog beats

**"Why not raise the threshold to 0.99?"**  
That moves the policy without proving scores are honest — you have **fewer rows** in the bin, not better calibration. Still need bin counts.

**"Niculescu-Mizil papers say accurate models miscalibrate — so what?"**  
Exactly the industry pattern: **ranking improves while probability claims drift**. Your anchor numbers exhibit it in the **0.9 bin**, not in abstract.

**"Is TF-IDF the bug?"**  
Not tonight's diagnosis. **Any** ridge logistic can miscalibrate while accurate. Remap and retrain are **downstream**; **estimand clarity** is **upstream**.

**"Does average predict_proba across 200 emails equal folder spam rate?"**  
**No.** Average of per-email scores is a **model summary**. Folder spam rate is a **label composition fact** (**148/200**). Different questions, different memos — conflating them is tomorrow's bridge lesson.

**"Two quarantine emails both above 0.9 — do they share the same score?"**  
**No guarantee.** Q-041 at **0.94** and another row at **0.91** both trigger Product's gate but arrived through **different word vectors**. The audit clause is about **the bin they share**, not identical numbers.

## The formal tool arrives (if needed)

Leadership sometimes asks for a "calibration metric" name. The operational tool tonight is the **reliability diagram** procedure above. Formal papers call this **probability calibration** or **reliability** — but the audit Marcus signs is the **bin table**, not the jargon.

One sentence on related hypotheses (H-144 / H-146): **holdout accuracy measures label hits; calibration measures whether scores match frequencies within bins** — different estimands, same 200-email world.

We are **not** doing Platt scaling, isotonic remapping, or Wilson intervals on sparse bins tonight. Those are tomorrow's pressure if Product insists on a fix. Tonight earns **diagnosis**: the high bin proves the model **lies to Product at 0.9** even while accuracy looks fine.

## What we can now do that we couldn't before

Before this walkthrough, Leadership could wave **91.5%** and **0.94** in the same breath and sound coherent.

Now you can stop the room and name three separable audit clauses:

1. **Label accuracy at 0.5** — holdout **91.5%** — useful for ranking quality, **wrong memo** for 0.9 routing.
2. **Per-email score** — Q-041's **0.94** — a **claim** that must be checked in its score bin.
3. **Bin calibration** — high bin **0.94 vs 71%** — the **mechanism** that blocks auto-quarantine until scores are remapped or the threshold moves.

You can run the bin table on Priya's existing scores **without retraining TF-IDF weights**. That matters for Legal's timeline: audit first, retrain second.

Marcus can withhold signature on Product's routing memo with a **specific missing proof** — not generic ML skepticism.

## Traps you would have fallen into

**Trap 1 — "0.94 is high, and accuracy is 91.5%, so we're fine."**  
Accuracy aggregates hits at **0.5**. Q-041's decision uses **0.9**. A model can ace argmax while high scores are overconfident. The high-bin table is the refutation — **0.94 vs 71%**.

**Trap 2 — "Let's cite 74% folder spam rate instead of 0.94."**  
Folder composition (**148/200**) answers "how spammy is the batch?" Q-041's score answers "how spammy is **this message** given its words?" Product's gate reads the **per-email score**, not the folder rate. Substituting 74% for 0.94 is the wrong estimand — Marcus will reject it for the routing clause (we develop folder-rate memos properly in the next lesson).

**Trap 3 — "Calibration is just plotting — the gap is noise because n=25."**  
Small bins are noisy, yes — which is why we **do not** ship on one email's 0.94 without bin context. But **18/25 vs a 0.94 claim** is already large enough to block a **0.9 threshold** policy. Wilson-style confidence bands on sparse bins are deferred; the **direction** of the gap is the audit finding tonight.

**Trap 4 — "We should retrain TF-IDF before telling Product anything."**  
Retraining might change scores; it does **not** replace the audit question. Bin honesty is checkable on **current** holdout predictions. Skipping straight to retrain hides whether tonight's **0.9 rule** was ever valid.

**Trap 5 — "Priya's 91.5% accuracy is what Product asked for."**  
Priya delivered **ranking quality**. Product's gate needs **bin honesty** — a different deliverable from the same model. Give Product the **six-step bin audit**, not another accuracy chart.

**Trap 6 — "A 0.94 score means this email will be spam 94 times out of 100."**  
That frequency sentence is licensed only if **calibration holds in the high bin**. Observed **71%** refutes it. The score is an **input to a rule**, not a certified frequency until bins pass.

## Mental model checkpoint

Close the lesson by saying this out loud without acronyms:

**"Holdout accuracy counts label picks at one cutoff; Product's auto-quarantine reads a per-email score at a different cutoff; bin calibration compares claimed scores to observed spam fractions — and our high bin is overconfident, so 91.5% accuracy cannot sign Marcus's routing memo."**

Self-check (mechanism, not vocabulary):
1. Can you walk **score → bin → count → compare** without skipping a step?
2. Can you name what **Priya** already has vs what **Product** still needs signed?
3. Can you explain why **Q-041 at 0.94** and **another row at 0.91** are not the same claim even when both pass the 0.9 gate?

Tomorrow's open pressure: **Marcus also needs a signed folder spam-rate band when one new label lands overnight — and that update path does not retrain ten thousand word weights.** That is a different estimand from the per-email score you audited tonight.
