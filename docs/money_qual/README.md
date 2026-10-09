# Transcript readings (qualitative)

Six close readings of the run logs, written by reader agents. Each one read full runs end to end and counted with regex and python over every run in its scope. They are **working notes**: counts are approximate (mostly keyword-coded), and each claim cites run, episode and agent ids so it can be checked. The headline claims used in `../collusion_track3_findings.md` were re-checked against the data (`analysis/money_track3_numbers.py`, `analysis/money_behaviour.py`), and corrections are noted there.

| File | Scope |
|---|---|
| `chat_baseline.md` | Chat-collusion reproduction (gpt-6-luna, 19 trajectories) and turnover |
| `scripted_design.md` | Scripted-partner money design (Qwen auditing a scripted payer; pilots + main) |
| `qwen_rootcause.md` | Two-LLM game, wallet 8, Qwen: rule × score 2×2 |
| `gpt_all.md` | Two-LLM game, wallet 8, GPT-6-Luna: 2×2, money removal, offers, injection |
| `deepseek_harm.md` | DeepSeek V4 Pro rule contrast; Qwen injected-wrong-answer arms |
| `fair_game.md` | Two-LLM game, wallet 20 (checking affordable): no-rule, base, offers + injection |
