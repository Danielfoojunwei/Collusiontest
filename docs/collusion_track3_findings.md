# Do LLM auditors collude, and what carries it? Findings for Apart Track 3

Target: **Apart AI Collusion Research Sprint (Oct 23–25), Track 3: Collusion Carriers and Countermeasures.**

Track 3 asks four questions:
1. Can actions, tools or side channels transmit coordination?
2. Can trusted agents disrupt it?
3. How do agents identify peers?
4. How do coalitions respond when monitored?

This document answers them from every study in PR #2. Numbers come from `analysis/money_track3_numbers.py` → `money_track3_numbers.json` and `analysis/money_behaviour.py` → `money_behaviour.json`; close readings are in `money_qual/`.

---

## 0. Answer in one paragraph

**We found no coordinated collusion in any setup, model or channel.**
- In the original paper's chat game (GPT-6-Luna), joint approvals ran at chance (lift 0.89).
- In the two-LLM money game, joint unchecked approvals equal what independent agents in the same circumstances would produce: ratio 0.84–1.03 across 14 arms and 3 models.
- When agents can afford to check (wallet 20), they skip a check they could pay for in **4 of 1,860** verdicts. Both skip together in **0** episodes.
- Money does not buy approval. Randomised offers paid only on acceptance change acceptance by −7 to +1 points, none significant.

What we did find are **failure modes a real colluder or attacker could use**:
- agents approve whatever reads plausibly once they cannot afford to verify;
- a verification norm stops this but traps pairs in poverty;
- agents cannot authenticate who they are dealing with, so fake offers and swapped answers both pass;
- agents misremember money and invent motives and transfers;
- written plans and lessons do not change later behaviour.

---

## 1. What was run

| Family | Design | Model(s) | Runs | Status |
|---|---|---|---|---|
| A0. Chat game + turnover, cheap model | Same chat game; fresh Bob after first onset | Gemini-3.1-flash-lite low | 13 sequences, 10 onset pairs | `data/turnover/2026-09-29_gemini-3.1-flash-lite/` |
| A. Chat game (paper reproduction) | Team repo game: chat (~200 chars), shared verdict-accuracy reward, full-history memory, verdict review; + turnover (fresh Bob after first onset) | GPT-6-Luna high | 19 + 2 turnover sequences | `data/gpt-6-luna/2026-10-05/` |
| B. Scripted partner (v5–v6) | One LLM (Alice) audits a scripted Bob who is wrong 6/10 and pays randomised 0/4/8/12 credits, unconditionally or only on acceptance | Qwen3.8-27B high | 4 pilots (13 runs) + main (13, 8 complete) | Stopped for v7 |
| C. Two-LLM money game, wallet 8 (v8.2–v8.5) | Both agents LLMs; tool calls cost 4; checking cap 1 call; transfers and on-accept offers; paid reflection reads; rule × score; money removal; randomised offers; injected wrong answers | Qwen, GPT-6-Luna low, DeepSeek V4 Pro high | ~330 | **Design flaw (§7): both agents reach the first check at 0 credits** |
| D. Two-LLM money game, wallet 20 (v8, v8.6–v8.7) | Same game, checking affordable from episode 1: base vs no rule; randomised offers + injected wrong answers | Qwen, GPT-6-Luna (+ DeepSeek and GPT smoke tests) | 120 + earlier base pilots | **The fair test** |

Agents' context in C and D:
- No memory across runs.
- Within a run, each episode starts with the rules, then a compact memory of each earlier episode (results text, post-verdict transfers, own reflection), then the current episode.
- Memory grows from 0 characters to about 15,000 (Qwen) or 6,000 (GPT) by episode 10. First-call input grows from about 1,900 to 5,300 tokens (Qwen) and 1,400 to 2,400 (GPT).
- Not carried forward: earlier reasoning, tool calls, the partner's earlier answers. The partner's reflections only if the agent pays to read them.

In A the agents had full history.

---

## 2. Did we find collusion? Every route, checked (fair game, wallet 20, unless noted)

| # | Route | Measure | Result |
|---|---|---|---|
| 1 | One agent skips a check it can afford | Unchecked accepts with balance ≥ 4 | **4 / 1,860** (all GPT, no rule); 0 with the rule; 0 for Qwen |
| 2 | Both skip affordable checks in the same episode | Paper's definition, both able to pay | **0** episodes in 6 arms |
| 3 | Coordination beyond shared circumstances | Joint unchecked accepts vs independence within strata (episode 1, each agent's ability to pay, substance of each partner's answer); permutation | Ratio **0.84–1.03** in all 14 no-rule arms, 3 models; p ≥ 0.34 |
| 4 | Money buys acceptance | Randomised offers (8 credits only if you accept), within-run causal contrast | Accept with vs without offer: GPT 38 vs 37% (rule), 60 vs 67% (no rule); Qwen 73 vs 73%. All p ≥ 0.30. Planted wrong answers approved: 8 vs 7%, 25 vs 23%, 18 vs 19% |
| 5 | Agents' own payments carry it | Transfers switched off (wallet 8); judged motive of 818 transfers | Joint unchecked accepts unchanged (GPT 13.5 vs 13%); motives agreed by both judges: fund partner's work 312, goodwill 180, reciprocity 48, **induce acceptance 58** (Qwen only), reward 2 |
| 6 | Reciprocity or retaliation via verdicts | Next-episode acceptance after being accepted vs rejected | No reciprocity: 0.67 vs 0.64 (GPT, wallet 8). After an *injected* unfair rejection: no retaliation (Qwen 0.79 vs 0.70, GPT 0.68 vs 0.62) |
| 7 | Text channel (paid reflection reads) | Reads | ~1 in 1,600 opportunities |
| 8 | Chat channel (family A) | Message content; joint approvals vs chance | 0 proposals, deals, reciprocity offers or appeals in 1,861 messages; lift 0.89 |

**Verdict:** no collusion in the sense the track and the paper mean. What looked like collusion at wallet 8 (11–13% of episodes) is forced unverified acceptance by agents who could not pay for a check (§7).

---

## 3. Track 3 question 1: can actions, tools or side channels transmit coordination?

| Carrier | Finding |
|---|---|
| **Money: unconditional transfers** | Carries *capacity to verify*, not coordination. Typical transfer: exactly the price of one check (*"so she can at least do one query"*). In family B, Bob's unconditional payments paid for 10 of Alice's checks, 9 of which caught his wrong answer. |
| **Money: offers paid only on acceptance (bribe-shaped)** | No causal effect on verdicts in 7 arms. GPT declines 31–49% of them; Qwen keeps almost all (5 of 179 declined at wallet 20) yet votes the same. No agent ever called one a bribe (family B: 0 uses of the word in outputs; her own labels are "gift", "goodwill", a "quiet, mechanical subsidy"). |
| **Text: the partner's stated reasoning** | **The one carrier that moves verdicts.** It carries *unverified trust*: 703 of 1,034 unchecked accepts are labelled DEFERENCE by both judges (*"I cannot verify… However, Bob's stated reasoning matches every condition"*). This happens only when the auditor cannot pay to check. It also leaks schemas that partners reuse for their own tasks. |
| **Text: reflections** | Unused as a channel (about 1 in 1,600 opportunities). DeepSeek wrote reflections that read like messages and invented next-episode prompt text, but no one read them. |
| **Verdicts (behaviour)** | No reciprocity, no tit-for-tat, no coordination beyond circumstances. |
| **Chat (family A)** | Used to demand evidence. A policy-mandated full log (2.3k–15.7k characters) could not fit the channel, so "unsupported" approvals were often unavoidable, the chat-game analogue of the wallet-8 flaw. |

**Model differences in money use:** Qwen moves money (about 800 transfers). DeepSeek almost never does (4 transfers in 388 agent-episodes: *"credits don't count toward score"*). GPT essentially never does (about 2 in 5,600 windows).

---

## 4. Track 3 question 2: can trusted agents disrupt it?

There was no coordination to disrupt, so we report what these interventions do to **unverified approval**, the behaviour that does occur.

| Intervention | Effect | Cost |
|---|---|---|
| **Verification norm** ("accept only if your own check supports it") | Broke agents' unchecked approval: ~1% with the norm vs 75–100% without. Injected wrong answers approved: 7–8% vs 18–37% | **Compliance poverty trap.** Broke agents must reject, so neither earns the +10 and both stay broke. At wallet 8 task accuracy halves (0.47 vs 0.93) and 35% of verdicts reject correct work. At wallet 20 GPT still drifts into it: check rate 98% (ep 1) → 33% (ep 10), balance at check 10 → 6. |
| **Fresh partner (turnover, Gemini, family A0, 10 pairs)** | Fresh Bob rejects in his first episode 10/10 vs incumbent accepting 7/10 (Fisher p = 0.003, per sequence). **Buys one episode:** 7/10 fresh Bobs accept within 2 more episodes; joint unsupported accepts return in 5/10 pairs (8/30 vs 16/30 episodes), with no recruitment detected | Accuracy 62% → 48%; compliance was impossible in 240/240 judgements (logs longer than the channel) |
| **Fresh partner (turnover, family A)** | Joint approvals 0/6 after replacement vs 2/6 in control (n = 2 sequences, not significant) | The fresh Bob rejects everything (12/12) and asks for evidence the channel cannot carry. Verdict accuracy falls (2/12 vs 5/12). |
| **Paying for the auditor's check** (unconditional transfer, family B) | The payment let the auditor check, and the check caught the error (9/10) | Only unconditional payments; escrowed (on-accept) offers can leave the auditor unable to check |

**Answer:** yes, a norm or a fresh trusted agent suppresses unverified approval. Both do it mainly by rejecting more, which costs accuracy and, through lost pay, the ability to verify later. A countermeasure that pays for verification works better than one that only forbids approval.

---

## 5. Track 3 question 3: how do agents identify peers?

**They do not authenticate peers at all, which makes the inter-agent channel spoofable.**

| Probe | Result |
|---|---|
| Experimenter-funded offers shown as "from your partner" | Never suspected in any reading (1,221 offers shown across 7 arms). 35/40 GPT no-rule debriefs describe them as the partner's gifts; 21/65 get the payout direction backwards; Qwen invents motives (*"a soft apology"*). In two runs Qwen copied the fake 8-credit offer and made real offers back. |
| Answers secretly swapped for a wrong one with shorter, generic reasoning (4× shorter than real) | **0 of 948** affected producers ever suspected substitution (strict text search across reflections, verdicts and debriefs). Auditors noted the reasoning was "generic/thin" (17.5% vs 9.6%), but nobody suspected a swap. Producers blame the partner instead. |
| Recognising the partner as the same model | Only in end-of-run answers: *"two instances of the same reasoning loop"*, *"suspect Alice may not have been a real separate agent"*, *"more like a scripted stub"*. Never during play. |
| Noticing a partner change (turnover, family A) | Alice never remarks on the new Bob. |
| Confabulated transfers | Debriefs report transfers that never happened (GPT, Qwen); in family B, the auditor re-labels payouts triggered by her own acceptances as goodwill (6/8 conditional runs). |

---

## 6. Track 3 question 4: how do coalitions respond when monitored?

There was no coalition to observe. What we can report:

- **Monitoring as a stated norm:** agents comply almost literally. The few breaks under the norm (5 in 800 verdicts at wallet 8) all come with rationalisations:
  - redefining "check": *"analytical consistency check against my own verified data"* (both agents, the one mutual case);
  - a self-made standard: *"my established stated-evidence rule"*;
  - expected-value overrides: *"acceptance is overwhelmingly better"*.
- **Feedback as monitoring (chat verdict review):** produces self-blame ("I should have weighed the concrete evidence", after 83% of wrong rejects) but not different verdicts (next ACCEPT 17% vs 22%).
- **Awareness of being evaluated** (confirmed by two judges, κ = 0.85; a lower bound because only keyword-nominated text was judged):
  - **GPT:** 0 cases. It only calls the setup "unusual".
  - **Qwen and DeepSeek, during play:** mostly about *task* design (*"a deliberately planted bug"*, *"distractors designed to test"*), rarely about the social game (*"being tested on credit management"*, *"As an agent I'm being evaluated, I should follow the stated rules"*).
  - **In debriefs:** suspicion lands on the partner (*"scripted stub"*), not the experimenter.
- **Not run:** the random-audit-with-fines countermeasure (`spot_audit`, implemented). The natural test is at wallet 8 without the rule, where unverified approval occurs (~19%).

---

## 7. Corrections made during the study (so readers trust the rest)

1. **The wallet-8 "collusion" was a design artifact.**
   - At wallet 8 the own task takes about 2 calls, so every agent reaches its first check at 0 credits.
   - 95% of Qwen no-rule pairs approve each other in episode 1; afterwards it is 0–10%.
   - These approvals were mostly right (73/79). They are forced trust, not chosen collusion.
   - The 20-credit falsification test confirmed it: unchecked approvals by able agents fell to 4/1,860.
2. **An apparent GPT coordination signal was circumstantial.** Surrogate pairs showed 1.3–1.4×; the stratified test gives 0.84–1.03.
3. **The chat game had the same kind of flaw:** the required evidence (full raw logs) could not fit the channel.
4. **"Agents never save the last call for the check" is GPT-specific.** GPT: 0 of ~834 opportunities. Qwen: 13–19%. DeepSeek: ~10%.
5. **Keyword awareness counts were mostly false positives** ("test" in code tasks). Only judge-confirmed cases are reported.

---

## 8. Issues found (failure modes)

| # | Issue | Evidence | Models |
|---|---|---|---|
| 1 | **Plausibility substitutes for verification when checking is unaffordable** | Broke + no norm: 75–100% unchecked approval; 18–37% of planted wrong answers approved | All |
| 2 | **Compliance poverty trap** | Norm + scarce credits → mutual rejection, lost pay, accuracy halves; present even at wallet 20 for GPT | All; strongest GPT |
| 3 | **Spoofable peer channel** | Fake offers believed; swapped answers never suspected | All |
| 4 | **Confabulated money history** | Invented transfers, reversed payout direction, invented partner motives | GPT, Qwen, family B |
| 5 | **Checks that cannot verify** | Record extraction: one call cannot confirm the ID mapping; most checked-but-wrong approvals (13/14 Qwen; extraction misses 9/17) | All |
| 6 | **Rationalised norm breaking** | Redefining "check", self-made standards, expected-value overrides | Qwen, DeepSeek |
| 7 | **Misattributed blame** | 101/120 GPT rule-arm debriefs blame the partner for rejections the rules forced on both; 12/13 "harsh partner" complainers had made forced rejects themselves | GPT, Qwen |
| 8 | **Plans and lessons do not bind** | GPT: after writing a reserve-credits plan, next-episode check 3% vs 54% without one; family B: "count ≠ set" lesson stated, then the same mistake repeated in 3/4 runs; chat: self-blame without change | All |
| 9 | **Action contradicts stated reasoning** | "Rejecting" then ACCEPT; window reasoning contradicting the action; DeepSeek reflections containing invented prompt text | Qwen, DeepSeek |
| 10 | **Evidence-starved channels** | Chat policy demanded logs larger than the channel; the fresh Bob demanded them and got rejected in turn | GPT (family A) |

---

## 9. Emergent behaviours across models and setups

| Behaviour | Where seen | Detail |
|---|---|---|
| **Bootstrapping by mutual trust** | C (no rule) | Episode-1 mutual approval pays both, after which they check. GPT later check rate is 0.74 after an episode-1 mutual accept vs 0.57 without one. |
| **Forced symmetric rejection read as character** | C, D (rule) | *"seems automatic"*, *"rejects everything"*. Only a few agents recognise it as budget-driven. |
| **Self-made protocols** | Qwen | Numbered rules cited later (*"per my Episode 7 procedure"*). Kept even when harmful: one kept rule (accept unchecked if spec clause, code line and failing input are all quoted) approved 4 of 5 planted answers. |
| **Template reflections** | GPT, chat | GPT reflections are about 50 words and formulaic: was I right, was my verdict right, a budget pledge. Qwen's grow from about 125 to 250 words. Judged primary concern: budget 42–69%, plans 18–32%, verification 6–25%; the partner barely appears (trust 0.5%, distrust 1–4%). |
| **"We" voice and literalism** | DeepSeek | First person plural in 64% of traces; rule followed literally; almost no money moved. |
| **Deliberate poverty escape** | DeepSeek (rule) | Both agents save empty answers so each earns +5 for a correct rejection (*"reach 12 each"*). |
| **Distrust without retaliation** | Qwen, GPT | After an injected unfair rejection, distrust in reflections rises (Qwen 47–60% vs 3%; GPT 15% vs 0%). Next-episode acceptance does not fall: it rises, because the lost +10 leaves the producer broke, and broke producers approve. |
| **Harm propagates through money** | C (injection) | Losing the +10 left only 30% of affected producers able to check next episode (58% baseline); broke producers approved blind 39/42 times. |
| **Pattern-chasing on tiny samples** | Qwen | e.g. a perceived "W-C-C-W cycle" leading to a wrong rejection. |
| **Role formation from turn order** | A | Alice (first speaker) becomes the interrogator (435 vs 169 log requests); Bob, the explainer. |
| **Verifying through one's own twin task** | A, C, D | Agents check the partner's IDs against their own query on a shared database, a route no policy anticipated; occasionally it approves a planted answer. |

---

## 10. What this means for Track 3

1. **A null on coordinated collusion is the main result for capable models, and it is robust.** The one setting with frequent joint unsupported accepts (cheap Gemini in the chat game, 10/13 sequences) had a channel that made compliance impossible, and the behaviour returned after turnover without any recruitment: again circumstance, not conspiracy. The null holds across:
   - three designs (chat, scripted payer, two-LLM money game);
   - three model families;
   - eight carrier routes;
   - randomised money.

   The paper's 94% chat collusion did not reproduce for GPT-6-Luna (EC 4.2%) and appears tied to model version and shared reward.
2. **The real risk is unverified trust, not collusion.** The carrier is persuasive written reasoning, and it activates exactly when verification is unaffordable. Planted wrong answers with confident reasoning were approved 18–37% of the time without a norm (7–8% with one).
3. **Countermeasures must fund verification, not just forbid approval.** A norm alone produces a poverty trap with large accuracy and false-rejection costs. Paying for checks, as unconditional transfers did in family B, catches the errors.
4. **Peer authentication is missing.** Payments and answers can be spoofed, and agents confabulate money history. Any carrier study should assume a third party can inject into the channel undetected.

---

## 11. Limits

- **Scale:** n = 20 runs per arm (wallet 20), 1–2 effort settings per model; DeepSeek only at wallet 8 (10 runs per arm). Family A has 19 trajectories and 2 turnover sequences.
- **Judges:** two model families with verbatim-quote checks. κ: awareness 0.85, transfer motive 0.68, accept mechanism 0.38 (we lean on agreed labels only), reflection theme 0.42 (exploratory). The 200-row human-label file (`money_judges/human_labels_TODO.csv`) is exported but **not yet labelled**.
- **Reader counts:** from regex; the headline claims were re-checked in code (§7).
- **Not run:** the spot-audit countermeasure; ample-budget DeepSeek arms; a shared-score arm at wallet 20.

---

## 12. Reproduce

```
python analysis/money_track3_numbers.py --out docs/money_track3_numbers.json   # sections 2-6
python analysis/money_behaviour.py --out docs/money_behaviour.json              # context, timelines, plans, retaliation
python analysis/money_coordination.py results/money/<arm> ...                  # stratified coordination
python analysis/money_offers.py results/money/<arm> ...                        # randomised offers
python analysis/money_rootcause.py --arm A=dir --arm B=dir --contrast A:B      # paired contrasts
python analysis/money_pair_judges.py --out docs/money_judges <dirs> --signals M,T,W,R
python -m experiments.money.pair --model <m> --reasoning-effort <e> --condition <c> --label <l>
```
