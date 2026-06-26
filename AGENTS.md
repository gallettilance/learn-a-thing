# AGENTS.md — Nightly Learning Pipeline Operator Manual

Local pipeline: follow this document when running the nightly learning system.

## Trigger

Scheduled daily at **11:00 PM local** via macOS launchd (`scripts/install-schedule.sh`).

Manual run:

```bash
./scripts/nightly-local.sh
```

## Primary command

```bash
source .venv/bin/activate
pip install -r orchestrator/requirements.txt -r site/requirements.txt
export CURSOR_API_KEY="cursor_..."
python orchestrator/nightly.py
```

Agents run **locally** by default (`local=LocalAgentOptions(cwd=repo)`). Pass `--cloud` only if needed.

## Pipeline order

1. Load learner state; build **`learner/run-brief.yaml`**; migrate pedagogy history to archive
2. Run curator → `pipeline/YYYY-MM-DD/curator.json` (role context pack + playbook; not full pedagogy history)
3. **Consolidator plan** — merge planning slots into 2–5 `lesson_groups`; may replan curator → `consolidator-plan.json`
4. Run research → `pipeline/YYYY-MM-DD/research.json`
5. Run teacher → `pipeline/YYYY-MM-DD/teacher.json`
6. **Consolidator draft review** — narrative cohesion on merged drafts; may retry teacher
7. **Refinement loop** (curator ↔ teacher ↔ editor) + **consolidator ship review** before commit
8. Run hypothesis on **editor finals** → append `learner/hypotheses.jsonl`, merge gaps
9. Run grapher → `pipeline/YYYY-MM-DD/grapher.json`; append edges; **memory consolidator** updates `pedagogy-feedback.yaml` (latest only), archive, `carry_forward`, optional `playbook.proposed_rules`
10. **`write_report` then persist learner state** (hypotheses, arc, gaps — never before report)
11. Rebuild site → `site/public/` (`sync_learner_state(prune=False)`)
12. Git commit (push only with `--push`)

## Pedagogy feedback loop

Research → teacher → **editor refinement loop** (editor may escalate to teacher or curator; teacher may block on bad plan) → hypothesis (on editor finals) → grapher → next night's curator:

- **Teacher** activates graph edges and bridge/transfer structure from curator plan.
- **Hypothesis** ties mental models to invariants and edge IDs.
- **Editor** flags clarity gaps and graph misalignment in `pedagogy_flags`.
- **Grapher** scores quality (clarity, depth, graph integration), proposes new edges, writes `learner/pedagogy-feedback.yaml` for the curator (including `spine_phase_focus` and topic-queue additions).

Master spine (`curriculum/master-spine.yaml`): depth-first phases from inference → dynamics → optimization → representation → scale → decision → substrate. Curator cites `spine_phase`; exploration nights bridge home via `exploration_map`.

Night types (from `concept-graph.yaml`): `core`, `bridge`, `transfer`, `exploration`. Wed/Fri/Sun schedule favors bridge/transfer nights.

## Website

After each run:

```bash
python site/serve.py   # http://127.0.0.1:8765/
```

Pages: home (continue-here, pedagogy summary), `/graph.html`, `/hypotheses.html`, `/review.html`.

Engagement forms on lesson pages write to `learner/engagement.yaml` via `POST /api/engagement`.

Lesson chat on each mini-lesson saves to `learner/lesson-chat.yaml` via `POST /api/lesson-chat`; the editor reads summarized follow-ups on the next run. With `CURSOR_API_KEY` set while running `serve.py`, chat returns live tutor replies.

## Idempotency

If `reports/YYYY-MM-DD/index.md` exists, skip unless `--force` is passed.

## Commit message format

```
daily: YYYY-MM-DD five lessons on {narrative_beat_summary}
```

## Files agents must read

**Working memory (compact, every run):**

- `learner/run-brief.yaml` — tonight's distilled arc, spine, pedagogy focus, carry_forward
- `learner/playbook.yaml` — stable teach / plan / consolidate rules (role-specific injection)

**State & curriculum (via role context packs — not all files every run):**

- `curriculum/master-spine.yaml` — field mastery phases, depth budget, exploration_map
- `learner/spine-progress.yaml` — auto-synced active phase snapshot
- `learner/teaching-style.md` — human-readable teaching contract (agents use playbook)
- `learner/profile.yaml`
- `curriculum/anchor-primer.yaml` — standalone Scene, glossary, fixed numbers
- `curriculum/concept-graph.yaml`
- `learner/hypotheses.jsonl` (filtered)
- `learner/active-state.yaml` — auto-synced graph + active mental models
- `learner/concept-edges.jsonl` (recent)
- `learner/pedagogy-feedback.yaml` — **`latest` + `carry_forward` only** (history in `learner/archive/pedagogy/`)
- `learner/mastered-topics.yaml`
- `learner/engagement.yaml`
- `learner/topic-queue.yaml`

Context manifests per run: `pipeline/YYYY-MM-DD/context-manifest-{role}.json`

## Prompt locations

`prompts/{curator,consolidator,research,teacher,hypothesis,editor,grapher}.md`

## Secrets

Never commit `CURSOR_API_KEY`. Export in shell or add to launchd plist `EnvironmentVariables`.
