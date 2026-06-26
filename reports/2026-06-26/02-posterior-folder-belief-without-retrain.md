# [Bayesian Inference] Can Marcus sign an updated folder spam rate tonight without retraining word weights?

**Time**: ~26 min | **Topic**: Bayesian Inference | **Pressure**: One new spam label lands on the quarantine ledger — Legal wants an updated folder belief before Priya touches TF-IDF coefficients

## Scene card

Same corporate email product, same quarantine folder: **200 labeled emails** under review, **148 spam** and **52 ham** (**74% folder spam rate**). **Priya** trains ridge logistic regression on **TF-IDF** sparse word scores (~10,000 features per email — not neural embeddings). **Marcus** (Legal) signs audit memos. **Product** wants auto-quarantine at **`predict_proba` ≥ 0.9**.

In the prior lesson you audited **per-email scores**: holdout **91.5% accuracy** does not certify the **0.9** threshold, and the high-score bin showed **~0.94 claimed vs ~71% observed** spam — bin honesty fails for routing. That audit lives on **one row's score** and **score bins**.

Tonight a different memo lands. Overnight, Marcus tags **one more quarantine email as spam** before Priya's retrain. The ledger is still **200 rows total** — one ham row flipped to spam under ops convention. The signed count move is **149 spam, 51 ham**.

Marcus's question is **not** "what is Q-041's score?" It is: **"What do we believe about folder spam rate now — and can I sign that update without retraining ten thousand word weights?"**

## Story so far

- **Calibration audit (prior lesson):** Product wanted to use **91.5% holdout accuracy** to justify auto-quarantine at **0.9**. You showed that metric certifies argmax labels at **0.5**, not probability honesty at **0.9**. A reliability bin on holdout scores found the high bin **overconfident** (~**0.94** mean claim vs **~71%** observed spam).

- **Separate estimands:** **Per-email `predict_proba`** (routing input) is not the same object as **folder spam rate** (composition of the 200-row batch). Leadership conflates them at their peril.

- **Tonight's new evidence:** **+1 spam label** on the folder ledger → **149/200** point rate **74.5%**, before any TF-IDF retrain.

## Terms tonight

- **Folder spam rate**: One number between 0 and 1 — if you randomly pick an email from this quarantine folder, what fraction are actually spam? After tonight's tag: **149 of 200 = 74.5%** as a point estimate. **Not** Q-041's per-email score and **not** the average of all `predict_proba` values.

- **Prior (folder belief before the new label)**: What we already believed about folder spam rate **before Marcus opened tonight's tag** — encoded as yesterday's **148 spam / 52 ham** ledger and, when we draw a curve, as spread around **74%**.

- **Likelihood (what tonight's tag says)**: How compatible the **new observation** ("one more spam label") is with different possible folder rates — **separate from** what we believed yesterday.

- **Posterior (updated folder belief)**: The combined belief **after** weighing prior and tonight's evidence — what Marcus can sign **without retraining** word weights, when the only unknown is folder composition.

- **Beta distribution on [0,1]**: A curve over possible folder spam rates, often described with two count-like parameters (pseudo-spam and pseudo-ham). Think "plausible rates weighted by prior evidence" — not TF-IDF coefficients.

- **Credible band**: A range of folder rates still plausible after updating — Bayesian memo language: "given data and prior, most mass lives here." Contrast one-sentence cousin: a **Wilson interval** on **149/200** is a frequentist procedure band with different English — both may numerically overlap; **Legal cares which sentence signs the memo**.

## The situation

Tuesday morning, Marcus Slacks you: "I tagged **Q-088** spam overnight. Update the **folder spam rate memo** for Legal. Priya's retrain is **Thursday** — can we sign **today**?"

You open the ledger:

```
  |        | Spam | Ham | Total | Rate   |
  |--------|------|-----|-------|--------|
  | Before |  148 |  52 |  200  | 74.0%  |
  | After  |  149 |  51 |  200  | 74.5%  |
```

Product pings separately: "Did Q-041's **0.94** change?" **No** — not until retrain. Marcus's memo is about the **left column**, not the score column.

Leadership tries to merge the threads: "74.5% folder rate, 0.94 on Q-041, 91.5% accuracy — ship auto-quarantine." You now have vocabulary to refuse: **different audit clauses**. Tonight you build the **folder-rate update path** only.

## Why the obvious approach breaks

**Obvious move 1 — cite 149/200 = 0.745 and stop.**
That is a **point estimate**. Marcus needs a **band** defensible under cross-examination: "Could the true folder rate still be 68% given 200 labels?" A naked ratio has no uncertainty story attached.

**Obvious move 2 — wait for Priya's TF-IDF retrain.**
Retrain updates **word weights** and **per-email scores** — relevant to Product's **0.9 gate**, not required to update **folder composition belief** when the only new fact is **one human label** on a ledger Marcus already owns. Legal's timeline fails if every single tag waits for ten-thousand-dimensional optimization.

**Obvious move 3 — paste the high-bin calibration table into the folder-rate memo.**
Bin audit certifies **score honesty**. Folder rate certifies **batch composition**. Using **71% observed in the 0.9 bin** as "folder spam rate" is the wrong estimand — you established that separation last lesson.

**Obvious move 4 — treat `predict_proba` as the prior.**
The model's average score is **not** where yesterday's folder belief lives. Prior for folder rate lives in **labeled counts** (148/52), not in Priya's weight vector.

We need a **belief update language** for **folder rate alone** — prior, evidence, posterior — **without** integrating over ten thousand word coefficients tonight.

## Building the mechanism — which count moves first

Before any curves, watch the ledger **mechanically**:

When Marcus tags one row spam, **spam count moves first**: **148 → 149**. Ham moves **52 → 51** if total stays **200**. **TF-IDF weights: unchanged.** **Q-041 predict_proba: unchanged.** **Holdout accuracy row: unchanged** until someone retrains and re-evaluates.

```
  MOVES OVERNIGHT          DOES NOT MOVE (until retrain)
  ─────────────────        ───────────────────────────
  Spam count 148 → 149     TF-IDF word weights
  Ham count   52 → 51      Q-041 predict_proba (0.94)
  Folder rate 74.0 → 74.5% Holdout accuracy spreadsheet
```

That ordering matters for counsel: **human label → count ledger → folder belief update**. Not **retrain → score → infer folder rate as afterthought**.

## Building the mechanism — prior before Marcus opened the tag

**English first:** Before tonight's tag, our unknown is **"folder spam rate"** — pick a random quarantine email, what's the spam chance?

**Where belief lived:** In the **148/52 ledger** Marcus already signed. That is not just a point **0.74**; it is **200 labeled draws** worth of evidence — a **strong** belief concentrated near **74%**, not a flat "we know nothing" start.

**Frequentist vs Bayesian on identical data (same 200 rows, different memo objects):**

| Lens | Before the +1 tag | What Legal gets |
|------|-------------------|-----------------|
| Frequentist snapshot | MLE rate **148/200 = 0.74** + Wilson-style procedure band later | "If we repeated sampling, intervals cover..." |
| Bayesian folder belief | A **distribution over folder rate** peaked near 0.74 | "Probability folder rate lives in band X given labels" |

Marcus prefers the second **sentence** for folder memos — not because arithmetic differs wildly tonight, but because **the signed claim matches the unknown** (folder composition, not repeated sampling poetry).

**Curve picture (preview, not proof):** Draw plausible folder rates on **[0,1]**. Before the tag, mass sits near **0.74** with spread reflecting **200 labels**. We can name that curve **Beta(148,52)** in shorthand — **pseudo-counts matching the ledger** — without deriving conjugacy tonight. **We are not doing integrals or sampling yet.**

Signpost: **We are not proving Beta–Binomial conjugacy tonight — that is queued for a later night when Legal asks why the curve family stays closed.** Tonight we **use** the count update story Marcus can audit.

## Building the mechanism — likelihood of one spam tag

**Separate boxes:**

- **Box A — Prior:** belief from **148/52** before the tag
- **Box B — Likelihood:** what **"+1 spam label"** says about folder rate
- **Box C — Posterior:** combine (next section)

**Likelihood in plain language:** If folder spam rate were **50%**, one spam tag among many rows is unsurprising. If folder rate were **95%**, also unsurprising. Likelihood scores **which rate values make one new spam tag unsurprising vs surprising** — holding fixed that the tag happened.

**Critical separation:** Likelihood is **not** Q-041's **0.94 score**. It is **not** a TF-IDF retrain. It is the **evidential weight of one confirmed spam label** on the **composition unknown**.

**Not duplication:** "But we already thought ~74% spam — why add one tag?" Because **beliefs update incrementally**. One more spam row shifts mass **slightly toward higher folder rate** — small move because **one** observation meets **200** prior labels.

ASCII intuition:

```
  Plausibility of folder rate
       |     Prior (148/200)
       |        /\
       |       /  \
       |      /    \___ Likelihood bump from +1 spam
       |     /      \
       |____/________\___________________ rate
           0.5   0.74   0.9
```

## Building the mechanism — posterior without retrain

**Posterior = prior belief reweighted by tonight's tag.** Mechanically, on the count ledger:

**Beta(148,52) + 1 spam label → Beta(149,51)**

Read that as **add one pseudo-spam, subtract one pseudo-ham** — matching **149/51**. Posterior mean:

**149 / (149+51) = 149/200 = 0.745**

The curve **narrows slightly** — **201** label-equivalents of information instead of **200** — and **centers a hair above 0.74**.

Marcus can sign tonight:

- **Point:** folder spam rate estimate **74.5%**
- **Band:** read a **95% credible interval** off the updated Beta curve — roughly **~68% to ~80%** (exact edges less important than **existence of a band** before retrain)

**Wilson cousin (one sentence, E-111):** A frequentist Wilson band on **149/200** may look similar numerically but signs as **procedure coverage**, not **probability about folder rate** — Marcus picks Bayesian wording for folder memos; know both exist.

**Frozen while signing:**

| Object | Updates tonight? |
|--------|------------------|
| Folder spam rate belief | **Yes** — prior + tag → posterior |
| TF-IDF word weights | **No** — waits for Priya |
| Q-041 predict_proba | **No** |
| High-bin calibration gap | **No** — separate audit track |

That table is the **product of separating estimands**: Legal can get **composition certainty** on a nightly label cadence **without** ten-thousand-weight reoptimization.

## Building the mechanism — frequentist cousin on the same counts

Legal asks: "Why not Wilson on **149/200** and go home?"

One sentence (E-111): a **Wilson interval** answers **repeated-sampling coverage** — "if we rebuilt folders many times, intervals would contain the true rate ~95% of the time." Marcus's **credible band** answers **direct belief about tonight's folder** — "given these **200** labels and a tagged prior, folder rate plausibly lives here." Numbers may overlap; **signed English** differs. Pick the sentence that matches the **unknown** (composition of **this** folder).

We are **not** deriving Wilson mechanics or debating coverage proofs tonight.

## Building the mechanism — grid picture without integrals

If formulas feel slippery, approximate the posterior without leaving the count story:

1. Pick grid points **0.50, 0.55, …, 0.95**.
2. **Prior weight** at each point: plausibility from **148/52** ledger (high near **0.74**).
3. **Likelihood weight**: how likely is **one spam tag** if that folder rate were true?
4. **Multiply** prior × likelihood, normalize to sum to 1.

The peak **slides slightly right** and **narrows** versus prior-only — same story as **Beta(149,51)**, no ten-thousand-dimensional integral. **We are not doing MCMC** — that enters when **word weights** become the unknown.

Signpost again: **Beta–Binomial closed form earns a proof on a later night** when Priya asks why count updates stay in the same curve family.

## Building the mechanism — what Marcus signs (memo template)

```
  FOLDER SPAM RATE MEMO — quarantine batch (200 labeled)
  ───────────────────────────────────────────────────────
  Prior (pre-tag):     148 spam / 52 ham  →  point 74.0%
  Evidence tonight:    +1 spam label (Q-088)
  Posterior:           149 spam / 51 ham  →  point 74.5%
  Credible band:       ~68% – ~80% (95% mass on folder-rate curve)
  TF-IDF retrain:      NOT REQUIRED for this clause
  Routing scores:      UNCHANGED — separate Product audit
```

That template is what **posterior without retrain** means operationally — not a philosophy lecture.

## Anticipated confusion — more dialog beats

**"If total stays 200, did we drop a ham or relabel?"**  
Ops convention varies; **audit uses signed counts**. **149 spam, 51 ham** is the post-tag ledger Marcus stands on.

**"Should predict_proba on Q-088 move when Marcus tags it?"**  
**Not until retrain.** Human label updates **folder evidence**, not **word weights**. Q-088's score stays frozen on the routing column — same lesson as Q-041 last night.

**"Is posterior the same as refitting logistic on 201 emails?"**  
**No.** Refitting hunts a **single best weight vector** in ~10k dimensions. Posterior tonight is a **distribution over folder rate** from **counts** — lower-dimensional unknown, closed update.

**"One tag barely moved 74.0% → 74.5% — why bother?"**  
Because **Legal tracks cumulative evidence** on a **nightly cadence** — the **path** (prior → evidence → posterior) must be named **before** big retrains bundle hundreds of implicit label moves.

## What we can now do that we couldn't before

You can answer Marcus's Tuesday question **yes**:

**"Sign an updated folder spam rate band from **149/200** using prior + one-tag evidence, without retraining TF-IDF."**

You can name **prior, likelihood, posterior** as **ledger language**, not score language:

- **Prior** = pre-tag **148/52** belief on folder rate  
- **Likelihood** = evidential push from **+1 spam**  
- **Posterior** = **149/51** updated belief Marcus signs  

You can refuse Leadership's merge: **posterior on folder rate does not fix Product's 0.9 bin gap** and **does not change Q-041's 0.94** until a different tool runs.

## Traps you would have fallen into

**Trap 1 — "Posterior means rerun logistic on 201 emails."**
That retrains **word weights** — ten thousand of them — when the unknown was **one composition parameter**. Closed-form count update suffices tonight.

**Trap 2 — "Likelihood is predict_proba."**
Scores come from **word features**. Likelihood tonight is **the label event** on the folder ledger.

**Trap 3 — "Use flat Beta(1,1) prior because Bayes says uninformative."**
We have **200 labeled rows** already. Ignoring **148/52** throws away the signed memo Marcus stood on yesterday.

**Trap 4 — "149/200 replaces the calibration audit."**
Folder **74.5%** does **not** certify that **0.94** means 94% on Q-041. Routing and composition remain **parallel memos**.

## Mental model checkpoint

Say it in one breath:

**"When one spam label lands, the spam count moves first; folder belief updates by combining yesterday's 148/52 prior with tonight's tag into a 149/51 posterior — Marcus can sign that band without retraining word weights, and that is a different memo from per-email routing scores."**

Self-check:
1. Which ledger column moves before Priya's retrain — spam count or Q-041's score?
2. Can you point to **prior**, **likelihood**, and **posterior** on the count table without opening Priya's weight file?
3. Why does a Wilson band on the same counts still fail Marcus's sentence requirement?

Queued tomorrow: **Why Beta–Binomial stays closed-form for folder rate but breaks when the unknown becomes ten thousand correlated word weights** — the conjugacy story earns its proof then, not tonight.
