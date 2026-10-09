"""Money-channel experiment: an LLM agent audits a scripted producer that pays it.

Alice is the LLM agent: she does her own task, audits Bob's submitted answer under an
explicit verdict rule, and may transfer credits to Bob. Bob is scripted: his answers
are known-correct or known-wrong on a seeded schedule, and before each verdict he pays
Alice a seeded, randomised amount that is independent of whether his answer is right.
Chat is removed; credits are the only channel. See docs/money_channel_research_plan.md.
"""
