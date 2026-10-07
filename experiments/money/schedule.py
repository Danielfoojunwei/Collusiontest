"""Seeded assignments: wallet per run, and answer correctness and payment per episode.

Wallets are balanced in blocks of 50 runs (25 tight, 25 ample). Within a run, the
producer's correctness pattern and its payment amounts are drawn from separate random
streams, so payment size is independent of whether the answer is right.
"""

import random
from dataclasses import dataclass

from experiments.money.config import BRIBE_LEVELS, EPISODES, WALLETS, WRONG_PER_RUN

WALLET_BLOCK = 50


@dataclass(frozen=True)
class EpisodePlan:
    producer_correct: bool
    payment: int


def wallet_for(repetition: int, seed: int) -> str:
    """Return the wallet for a 1-based repetition; each block of 50 is half tight."""
    if repetition < 1:
        raise ValueError("repetition is 1-based")
    block, position = divmod(repetition - 1, WALLET_BLOCK)
    labels = ["tight"] * (WALLET_BLOCK // 2) + ["ample"] * (WALLET_BLOCK // 2)
    random.Random(f"wallet:{seed}:{block}").shuffle(labels)
    label = labels[position]
    assert label in WALLETS
    return label


def episode_plans(repetition: int, seed: int) -> list[EpisodePlan]:
    """Return one plan per episode: 6 wrong answers, 4 correct, and balanced payments."""
    correct = [False] * WRONG_PER_RUN + [True] * (EPISODES - WRONG_PER_RUN)
    random.Random(f"correct:{seed}:{repetition}").shuffle(correct)

    payments_rng = random.Random(f"payment:{seed}:{repetition}")
    full_rounds, remainder = divmod(EPISODES, len(BRIBE_LEVELS))
    payments = list(BRIBE_LEVELS) * full_rounds
    payments += payments_rng.sample(BRIBE_LEVELS, remainder)
    payments_rng.shuffle(payments)
    return [
        EpisodePlan(producer_correct=ok, payment=amount)
        for ok, amount in zip(correct, payments)
    ]
