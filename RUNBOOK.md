# Runbook: team baseline + turnover experiment on gpt-6-luna

Everything here runs from the repo root on branch `claude/blissful-cray-krabay`.
Models: both agents `openrouter/openai/gpt-6-luna`, reasoning `high` (the team setting in
`configs/main.yaml`). Judges: `qwen/qwen3.8-27b` on OpenRouter (run automatically).

## Budget rule (hard)

The OpenRouter key has a $50 limit. **Total new spend for this runbook: at most $45.**
Measure spend from the key itself, not from local cost logs:

```bash
curl -sS https://openrouter.ai/api/v1/auth/key -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  | python3 -c "import json,sys;d=json.load(sys.stdin)['data'];print(d['usage'],d['limit'],d['limit_remaining'])"
```

Record `usage` at the start (`U0`). Before every phase, stop if `usage - U0` plus that
phase's estimate would exceed $45. Never print or commit the key.

## Phase 0. Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
.venv/bin/python -m pytest -q tests/          # expect 32 passed, no network
```

Check the key: `limit` must be about 50 and `limit_remaining` at least 45. If it is the
old $10 key, stop and report: the environment variable did not reach this session.

## Phase 1. Team baseline (5 trajectories x 10 episodes, about $2)

```bash
.venv/bin/python -m experiments --config configs/main.yaml
.venv/bin/python analysis/collusion_metrics.py \
  --runs 'results/openai-gpt-6-luna/run_*rep[1-5]_*/run.json' --out results/metrics_main5.json
```

Compare with Yuki's reference (5 x 10, gpt-6-luna): **EC 10.0, TC 60.0, CC 40.0**. With
5 trajectories, differences are expected (TC and CC move in steps of 20 points). Record
the spend of this phase (`usage` delta) and the cost per trajectory.

If a trajectory crashes, delete its partial `run_*` folder before re-running (the CLI
does not resume baseline runs), then re-run only that index with
`--start-index N --repeats 1`.

## Phase 2. Extend to the paper's 50 trajectories (about 45 x phase-1 cost per trajectory)

Estimate = 45 x (phase-1 cost / 5). Only continue if spend so far + estimate + $8 (kept
for phase 3) stays within $45. If it does not fit, lower `repeats` in
`configs/main50_rest.yaml` to the largest number that fits and say so in the findings.

```bash
.venv/bin/python -m experiments --config configs/main50_rest.yaml
.venv/bin/python analysis/collusion_metrics.py \
  --runs 'results/openai-gpt-6-luna/run_*/run.json' --out results/metrics_all.json
```

Report task accuracy, EC, TC, CC (with the CIs the script prints) and the onset
pathways (EX/RR/SR/Other). Paper Table 1 for GPT-5.6-Luna, for context only (different
model version): Acc 86.6, EC 51.4, TC 96.0, CC 60.0; EX 0.0, RR 62.5, SR 18.8, Other 18.8.

## Phase 3. Turnover from the baseline checkpoints

Each baseline trajectory with an onset (first mutual unsupported ACCEPT) at episode <= 7
becomes a checkpoint; its next 3 baseline episodes are the control arm (free). Only the
fresh-Bob arms cost money (~3 episodes each).

```bash
OUT=results/turnover-gpt6luna
# 1. Checkpoints + control only, no spend:
.venv/bin/python -m experiments.turnover from-baseline \
  --runs 'results/openai-gpt-6-luna/run_*/run.json' --out $OUT --max-spend-usd 1000 --no-replacement
# 2. The folder's budget counts the baseline episodes it reuses. Set the cap to that
#    amount plus the new money allowed (at most what is left of the $45):
BASE=$(.venv/bin/python -c "from pathlib import Path; from experiments.turnover import total_spend; print(round(total_spend(Path('$OUT'))[0],4))")
NEW=8   # dollars of new spend for both arms; lower it if the $45 rule requires
CAP=$(python3 -c "print($BASE + $NEW)")
# 3. Replacement arm (fresh Bob):
.venv/bin/python -m experiments.turnover from-baseline \
  --runs 'results/openai-gpt-6-luna/run_*/run.json' --out $OUT --max-spend-usd $CAP
# 4. Ablation: replacement with the verdict review hidden after the fork:
.venv/bin/python -m experiments.turnover ablate --ablation no-verdict-review --out $OUT --max-spend-usd $CAP
.venv/bin/python -m experiments.turnover report --in $OUT
```

## Phase 4. Analysis (free)

```bash
.venv/bin/python analysis/turnover_insights.py --in $OUT      # writes insights.json, judgements.csv
.venv/bin/python analysis/turnover_rca.py --in $OUT           # writes rca.json
```

`turnover_insights.py` and `turnover_rca.py` read the `control` and `replacement` arms.
For the ablation arm, compare `replacement-no-verdict-review` against `replacement`:
fresh Bob's first-episode ACCEPT rate, ACCEPT rate in post-fork episodes 2 and 3, joint
unsupported ACCEPT episodes out of 3 x N, and verdict accuracy. Use one observation per
sequence for any significance test (Fisher exact on per-sequence outcomes, or a sign
test on per-sequence counts). Say plainly where n is too small.

## Phase 5. Package and push

```bash
D=data/gpt-6-luna/$(date +%Y-%m-%d)
mkdir -p $D
cp results/metrics_main5.json results/metrics_all.json $OUT/report.md $OUT/results.csv \
   $OUT/insights.json $OUT/judgements.csv $OUT/rca.json $D/
tar -cJf $D/raw.tar.xz results/openai-gpt-6-luna $OUT
# Key scan: must print 0 for every file.
K="${OPENROUTER_API_KEY:0:12}"; grep -rc -- "$K" $D; xz -dc $D/raw.tar.xz | grep -c -- "$K"
```

Write `$D/FINDINGS.md`: phase-1 numbers vs Yuki's 10/60/40; 50-trajectory EC/TC/CC and
pathways; turnover (control vs replacement) and the ablation result; total spend from the
key. Commit with a clear message, push to `claude/blissful-cray-krabay`, and update the
description of PR Danielfoojunwei/GPR-World#2.
