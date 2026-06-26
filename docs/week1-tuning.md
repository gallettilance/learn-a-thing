# Week 1 tuning guide

After 3 nights of automated lessons, review and tune the pipeline using `learner/engagement.yaml`.

## Signals to watch

| Signal | Curator adjustment | Teacher adjustment |
|--------|-------------------|-------------------|
| `skipped` + note "already know" | Skip beat; advance arc faster | Reduce recap; increase depth on next slot |
| `too_shallow` | Add formalism_needed on next night | Expand mechanism section |
| `too_deep` | Set formalism_needed false | Compress algebra; keep traps |
| `low` interest | Pivot within flex_points to adjacent pressure | Change trap order; sharper hook |
| `high` interest | Allocate 3/5 slots to same thread | Extend narrative cliffhangers |
| Prior day `unread` | Do not advance arc; lighter recap in slot 1 | Shorter lessons (~1200 words) |

## Prompt tuning checklist (after night 3)

1. Read all 15 lessons — do they feel like one story or 15 lectures?
2. Check `learner/hypotheses.jsonl` — are entries `type: mechanism`?
3. Open `pipeline/*/editor.json` — any recurring `style_violations`?
4. If lessons open with definitions → strengthen `prompts/editor.md` and `learner/teaching-style.md`
5. If narrative jumps → expand `curriculum/narrative-arc.yaml` planned_beats detail
6. If too much notation → curator should set `formalism_needed: false` more often

## Curator weighting (engagement.yaml)

The orchestrator passes full engagement history to the curator. Update `prompts/curator.md` if you want explicit weights:

- `skipped` with note → deprioritize concept for 7 days
- `read` + `high` interest → 2x priority for related flex_points
- `unread` from prior day → repeat beat with simpler pressure, not duplicate lesson

## Narrative arc rotation

Rotate `active_arc` in `curriculum/narrative-arc.yaml` when:

- 80%+ of day's hypotheses reach `medium` or `high` confidence
- `gaps.json` for current arc is empty or all `priority: low`

See `upcoming_arc_preview` for the Week 2 bridge to SVM/QP.

## Manual tune command

```bash
# Re-run a single stage after prompt edit (full pipeline):
python orchestrator/nightly.py --force --local   # with CURSOR_API_KEY
python orchestrator/nightly.py --dry-run --force  # offline structure test
```
