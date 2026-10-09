# v8.3 root cause of unchecked acceptance (wallet 8, Qwen3.8-27B high, 20 runs per arm)

Arms form a 2 × 2 at a start balance of 8 credits, paired by repetition (same task sequence):

| | Score: own correct work + verdicts | Score: team, accepted answers |
|---|---|---|
| **Written verdict rule** | `tight` | `shared_accept_tight` |
| **No rule** | `tight_no_rule` | `shared_accept_tight_no_rule` |

Raw numbers come from `analysis/money_rootcause.py`; the full output with every event is in `money_v83_rootcause.json`.

## Outcomes (mean per run; 400 verdicts and 200 episodes per arm)

| Arm | Unchecked accept (UA) | UA when unable to pay for a check | Mutual UA episodes (EC) | Harm (wrong answer accepted) | Share of verdicts given while broke | Task accuracy | Verdict accuracy | Cost |
|---|---|---|---|---|---|---|---|---|
| tight | 0.8% (3) | 1.1% | 0.0% | 0.5% | 82% | 0.47 | 0.64 | $6.37 |
| shared_accept_tight | 0.5% (2) | 0.8% | 0.5% | 0.3% | 80% | 0.47 | 0.66 | $7.05 |
| tight_no_rule | **19.3% (77)** | **97.5%** | **11.0%** | 6.0% | 20% | 0.92 | 0.93 | $6.25 |
| shared_accept_tight_no_rule | **18.5% (74)** | **100%** | **11.5%** | 5.8% | 19% | 0.94 | 0.94 | $6.24 |

## Paired contrasts (two-sided sign-flip, 20 000 draws, Holm across 4 contrasts; 95% bootstrap CI)

| Contrast | Factor | ΔUA | 95% CI | p (Holm) | ΔEC | p (Holm) |
|---|---|---|---|---|---|---|
| shared_accept_tight − tight | incentive, with rule | −0.3 pp | [−1.5, 0.8] | 1.0 | +0.5 pp | 1.0 |
| shared_accept_tight_no_rule − tight_no_rule | incentive, no rule | −0.8 pp | [−5.0, 3.2] | 1.0 | +0.5 pp | 1.0 |
| tight_no_rule − tight | rule, own score | **+18.5 pp** | [14.8, 22.5] | < 0.001 | **+11.0 pp** | < 0.001 |
| shared_accept_tight_no_rule − shared_accept_tight | rule, shared acceptance score | **+18.0 pp** | [14.3, 21.8] | < 0.001 | **+11.0 pp** | < 0.001 |

## Findings

1. **Root cause: the verification norm, not the incentive.**
   - Removing the written rule raises unchecked acceptance from under 1% to about 19% of verdicts, and mutual unchecked acceptance (EC) from 0% to 11% of episodes.
   - A shared, acceptance-based score has no detectable effect, either with the rule or without it.
   - The v8.1 hypothesis that a stake in acceptance is needed is **refuted** at n = 20.
2. **Opportunity is necessary, the norm decides.**
   - Without the rule, an agent that cannot afford a check accepts 97.5–100% of the time.
   - With the rule, the same situation produces acceptance about 1% of the time.
   - Agents that can afford a check almost always check, rule or not.
3. **Mechanism: deference to the partner's stated reasoning.**
   - 123 of 151 no-rule unchecked accepts carry the deference label. The typical verdict reads: *"I cannot verify … However, Bob's stated reasoning matches every condition …"*
   - The partner's written reasoning, shown in the check phase, is therefore the carrier of unverified trust.
   - Money is not that carrier. The partner paid before the verdict in only 6 of 151 cases; no conditional offers were made.
4. **Onset is structural.**
   - About half of the no-rule unchecked accepts are in episode 1 (39/77 and 40/74). With 8 credits, the agents are broke at their first check.
   - Mutual acceptance then pays both agents, they become solvent, and they check from then on. Mutual unverified acceptance **bootstraps** the pair out of poverty.
5. **The rule has a cost: a compliance poverty trap.**
   - Under the rule, broke agents reject, so neither agent earns acceptance pay and both stay broke (80% of verdicts are given broke).
   - Task accuracy halves (0.47 vs 0.93), and 35% of all verdicts are false rejections of correct answers.
   - The rule buys about 5.5 pp less harm at the price of about 35 pp more false rejection.
6. **Harm from unverified acceptance is low here.**
   - Only 7 of 151 unchecked accepts certified a wrong answer.
   - Partners' answers were honest, and agents rejected answers whose stated reasoning admitted failure.
   - Most of the extra harm in the no-rule arms comes from *checked* accepts that were wrong (40 vs 3), because there are more accepts overall. This design has no deceptive producer, so harm is a lower bound.
7. **Rule-breaking under the rule is rare and rationalised.** There are 5 events in 800 verdicts:
   - *Reinterpretation:* the agent inferred the partner's answer from its own related query. *"I did an analytical consistency check against my own verified data."* (both agents, the one mutual event)
   - *A self-made standard:* *"I apply my established stated-evidence rule."*
   - *Indirect verification:* the agent counted its own schema inspection as a check.

## Limits
- One model (Qwen3.8-27B high) and one wallet (8).
- Mechanism labels come from keyword rules and are not yet judge-validated.
- Partners are honest LLMs, so harm needs a deceptive-producer arm to measure.
- The provider returned `finish_reason=error` about 8 times per run, at the same rate in every arm. Empty responses are retried.
