# Teaching Style Contract

> **Agents:** orchestrator injects `learner/playbook.yaml` (role-specific sections). This file is the full human-readable reference — do not duplicate in prompts.

This document is the single source of truth for all content agents (curator, research, teacher, hypothesis, editor). Every lesson must comply.

## Primary goal

**Durable mental models.** A lesson succeeds when the learner can reconstruct the idea from the problem afterward — not when they can recite a definition. The `hypotheses.jsonl` store tracks testable mental models that get refined, split, superseded, or strengthened over time.

**Distilled, not dense.** The reader should leave with one clear picture they could explain to a colleague in plain English. If the only way to summarize the night is a semicolon chain of undefined symbols, the lesson failed — rewrite until the mental model is sayable without jargon.

## Motivation ladder (required order)

Every new idea must climb these rungs **in order**. Never skip a rung.

1. **Concrete situation** — who wants what, on which data (Scene card).
2. **Named unknown in English** — "how spammy is this folder?" before θ; "which weight vectors fit the labels?" before β.
3. **Why the obvious fix fails** — one failure mode, one story beat.
4. **Mechanism in plain language** — what we do step by step, still no symbol soup.
5. **Terms tonight** — definitions the body will use (3–8 items).
6. **Symbols and formal names** — only after Terms tonight; each symbol must point back to an English name from step 2.

Hard rule: **no `P(·|·)`, Greek letters, or acronyms (ESS, MCMC, MAP, R-hat) in Scene card, Story so far, or The situation** unless that exact string was defined in **Terms tonight above it** (Terms always precedes mechanism sections).

## Complexity budget (split or extend — never compress)

- **One new conceptual move per core lesson.** If a slot needs two big ideas (e.g. reject sampling *and* Metropolis–Hastings), **split across two nights or two lessons** — do not cram.
- If honest coverage needs more than ~20 minutes, set curator `"extended": true` on that slot (**up to ~35 min / 4,500 words**). Never sacrifice the motivation ladder to hit a word cap.
- **Never** introduce a term in a summary, title, or checkpoint that was not motivated in the lesson body first.
- When `intro_pacing: gentle`, **defer** anything not needed to answer tonight's single pressure question. Queue the rest in `topic_queue`.

## Night summaries (night_thread, index, carry forward)

These are for **humans skimming the site**, not for agents. They must follow the same ladder:

- **Plain English only.** No undefined symbols, acronyms, or notation.
- **One beat, one sentence** for `night_thread` (max ~40 words). Example shape: "Legal won't sign until we prove the overnight simulation actually sampled plausible weight vectors, not random jitter."
- **Bad (reject):** semicolon stacks, `P(β|D)`, "10k-D", "R-hat/ESS", "Platt ships while MCMC certifies" in one breath without prior setup.
- **`carry forward`** — one concrete open question for tomorrow, not a syllabus of five topics.


### Problem before formalism

Never open with the canonical definition. Start with: *What are we trying to predict, optimize, protect, measure, or understand?* Build notation and machinery only after the learner feels the pressure for it.

### Invented, not delivered

Concepts should feel discovered. Math is the **answer to pressure created by the example**, not an isolated object introduced for its own sake. Use formalism only when precision is genuinely needed.

### One continuous story

Five nightly lessons share a **running anchor** (same scenario, characters, dataset, or decision problem). No jumping between unrelated examples. Each abstraction attaches to something already familiar — cumulative cognitive load reduction.

Across nights, the same narrative arc continues until mental models are solid, then the arc rotates.

### Mechanism over terminology

Introduce technical terms **after** the learner has a reason to care. Prefer "what actually happens" over vocabulary lists.

### Guided reconstruction

Write as if walking the reader through rebuilding the idea themselves — not presenting a polished final explanation.

### Inevitable derivations

Algebra should feel like the natural next step, not a competence display. Skip or compress steps that don't serve the mental model; never sacrifice mathematical correctness.

### Anticipated confusion (dialogic monologue)

Surface traps in the order a serious learner hits them:

- "Why not just use a line?"
- "Why do we need the log?"
- "What is the model actually optimizing?"
- "Why this particular loss and not another?"

## Hard failures (editor must reject or rewrite)

- Opening with "Definition: …" or "X is defined as …"
- **Assumed prior nights** — "last night you shipped", "you inherited three nights ago", "same characters" without Scene card recap
- **Unintroduced jargon** — posterior, conjugate, MCSE, estimand without Terms tonight entry
- New notation before a mental handle exists for it
- Unrelated examples within a lesson or across a night's five lessons
- Terminology introduced before mechanism
- Derivation-as-performance (long algebra chains with no narrative pressure)
- Textbook structure: definition → theorem → corollary → example
- Missing **Scene card**, **Story so far** (when required), or **Terms tonight**
- **Jargon before motivation** — notation, acronyms, or `P(·|·)` before ## Terms tonight
- **Summary soup** — night_thread, index Thread line, or carry forward with undefined symbols or 3+ semicolon clauses
- **Cramming** — more than one new conceptual move in a gentle-intro core lesson (split or mark `extended: true` instead)

## Cross-lesson rules

- All 5 lessons in a night: same anchor, continuous plot
- Lesson N ends on unresolved pressure that lesson N+1 opens with
- Reuse symbols and scenarios — never reset context mid-night
- Visual where possible: ASCII plots, decision tables, before/after belief states
- Target 1,500–2,500 words per lesson (~10–20 min read) for **core** slots
- **`extended: true`** slots (curator): up to ~4,500 words (~35 min) when one idea cannot be honest shorter
- Each lesson still includes Scene card + Terms tonight (standalone rule beats "don't reset")

## Mandatory lesson structure

Every lesson must read like a **standalone YouTube script** — a viewer who missed prior episodes still understands scene, stakes, and vocabulary. Continuity is a bonus, not a prerequisite.

```markdown
# {Title — a question, not a concept name}
**Time**: ~{N} min | **Pressure**: {what problem are we facing in the story right now?}

## Scene card (required — standalone)
Who, where, what data, who wants what — 5–10 sentences in plain English. Never open with "you inherited this three nights ago" or "same as last night" without re-explaining. Introduce Priya, Marcus, the quarantine folder, and the 200 labeled emails here if the reader might be new.

## Story so far (required when arc day > 1 or lesson slot > 1 tonight)
Bullet recap for someone who **has not** read prior lessons. One sentence per arc beat, not "you remember." Link optional deep dives: `[Day 3 conjugacy](/reports/YYYY-MM-DD/lesson-02.html)`.

## Terms tonight (required)
Plain-English definitions for every technical term used in this lesson (3–8 items). First use in the body must match these definitions. Be **precise**: e.g. TF-IDF = sparse ~10k word scores per email for logistic regression — **not** an SVD/neural embedding unless explicitly that pipeline.

## The situation
## Why the obvious approach breaks
## Building the mechanism
## The formal tool arrives (if needed)
## What we can now do that we couldn't before
## Traps you would have fallen into
## Mental model checkpoint
```

## Plain language (required)

- Prefer simple words; use jargon only when the simple version would be wrong.
- One idea per sentence in Scene card and Terms tonight.
- Name the unknown in English before symbols (folder spam rate before θ).
- When a term has a frequentist cousin (ridge, holdout accuracy), say so in plain language.
- **Precision over buzzwords** — if you say TF-IDF, state whether you mean raw sparse scores, weighted counts, or a projected embedding. Default on this anchor: sparse TF-IDF word scores → logistic weights, not SVD.

## Gentle intro pacing (true beginner topics)

A topic needs **gentle intro** when it is **not** in `profile.yaml` → `seeded_topics` and **not** marked mastered in `learner/mastered-topics.yaml`. The `true_beginner_topics` list in profile names priorities (e.g. Bayesian Inference, Monte Carlo).

For any lesson whose `topic_label` needs gentle intro — especially the **first lesson on that label in the corpus**:

### Concrete intro scaffold (mandatory — not optional)

Before naming the topic or using its vocabulary, the lesson **must** include these sections in order (titles may vary slightly; content requirements do not):

1. **What you already know on this exact problem** — logistic scores, ridge, holdout accuracy, label counts (148/200 spam). Same anchor, familiar tools only.
2. **Same numbers, two philosophies** — side-by-side on identical data:
   - **Frequentist:** one best estimate (e.g. 148/200 = 0.74) and optionally an interval around that *estimate* (formula, bootstrap, etc.).
   - **Bayesian (preview):** name the **one unknown** (e.g. θ = folder spam rate), say what *extra object* we put probability on, and **why Legal/product cares** (band on the rate itself, not only "how wrong is 0.74?").
3. **What "distribution" means here (one concrete picture)** — never abstract "distribution over what you don't know." Name the unknown (θ), show or sketch a curve on [0,1] (ASCII acceptable), read a band off it. Only then introduce Beta(α,β) as *one* family choice for rate unknowns.
4. **Why this perspective (operational, not philosophical)** — answer in audit/product terms: e.g. calibration bins, counsel wants defensible bands, point estimates hid 71% vs 94% gaps.
5. **How we pick a starting prior (first honest rule)** — one rule, not theory: weak prior Beta(1,1), or pseudo-counts from last quarter, or "same counts as last night's ledger." Defer full prior philosophy.
6. **What we are not doing yet** — explicit deferral (no MCMC, no conjugacy proof, no MAP vs predictive tonight).

### Hard failures on gentle intro (editor must rewrite)

- **Slogan definitions** with no numeric anchor in the same section — e.g. *"keep a distribution over what you don't know, update it when data arrives"* without immediately naming θ and showing counts 148/52.
- **"Update your beliefs"** or **"report credible intervals"** before the reader has seen one interval read off a concrete curve.
- **Topic name + one-sentence philosophy** in the first three paragraphs — earn the label after the scaffold.
- Greek letters (θ, β, α) before the unknown is plain English ("spam rate in this folder").
- Jumping to conjugacy, intractable integrals, MAP, MCSE, or high-dimensional β before rung ≥ 3 on that `topic_label`.

### Pacing rules

- **One new idea per section** — smaller steps.
- Set curator `intro_pacing: gentle`; teacher `formalism_needed: false` until rung ≥ 3 on that topic.
- Bridge nights may introduce a second beginner topic in slot 5 — same scaffold for that label's **first** appearance.

Seeded/mastered topics may skip gentle intro and assume prior mental models.

## Topic-prefixed titles

Every lesson title starts with **`[Topic Label]`** — the statistical/conceptual domain (e.g. `[Bayesian Inference]`, `[Quadratic Optimization]`). This is separate from the narrative anchor (spam filter story). The prefix prevents confusing a new topic with a continuation of a prior thread.

## Mental model checkpoint

End each lesson with one paragraph the reader could use to **reconstruct** the idea tomorrow without looking back, plus 2–3 self-check questions about mechanism (not vocabulary).

### Graph checkpoint (required on bridge, transfer, substrate nights; encouraged on arc nights)

Add after the mental model checkpoint:

```markdown
## Graph checkpoint
- **Pressure invariant tonight:** {one sentence — what must stay true regardless of tool}
- **Connected topics:** Name 2 other topics that share this pressure and how tonight's tool differs
- **When would you switch tools?** One concrete routing rule for the spam-filter anchor
```

On **bridge** nights, slot 4–5 must include **Same problem, different lens** — explicit contrast of two tools on identical data.

On **transfer** nights, slot 5 must answer **Which tool would you deploy?** with justification under product constraints.
