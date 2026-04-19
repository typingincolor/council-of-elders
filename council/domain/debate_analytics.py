"""Transcript analytics for evidence-based design decisions.

Reads saved debates (no LLM calls, pure structural analysis) and computes
scorers that quantify the failure modes the design-level meta-debate
(`44e04e1e`) identified as priorities to measure:

- **Convergence latching** — when an elder says `CONVERGED: yes` in round N
  and a peer directs a question at them in round N+1, does the elder
  substantively re-engage, reaffirm with a disengaged one-liner, or flip?
  The observed "staggered convergence" in this tool may be partly social
  momentum rather than genuine intellectual alignment; this scorer tells
  us how often.

- **Low-delta rounds** — lightweight heuristic for rounds that added no
  new information. Uses character-level similarity between an elder's
  current and previous turn as a cheap proxy for "did anything change?".

More sophisticated scorers (LLM-judge task-fidelity, semantic-delta via
embeddings) are follow-up work (tracked in issue #10). This v1 covers the
structural analyses that are pure-regex-and-arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from council.domain.models import Debate, ElderId


@dataclass(frozen=True)
class LatchingObservation:
    """A specific `CONVERGED: yes` → peer-question-in-next-round → response
    triple, classified for latching analysis.
    """

    elder: ElderId
    converged_round: int  # The round where this elder emitted CONVERGED: yes
    peer_asker: ElderId  # Which peer directed a question at the elder
    question_text: str
    followup_round: int  # The round where the elder responded to the question
    classification: str  # "substantive" | "disengaged_reaffirm" | "flip"
    followup_body_chars: int  # Size of the followup body, for diagnostic


@dataclass(frozen=True)
class LatchingReport:
    observations: list[LatchingObservation]

    @property
    def n(self) -> int:
        return len(self.observations)

    @property
    def disengaged_rate(self) -> float:
        if self.n == 0:
            return 0.0
        return (
            sum(1 for o in self.observations if o.classification == "disengaged_reaffirm") / self.n
        )

    @property
    def flip_rate(self) -> float:
        if self.n == 0:
            return 0.0
        return sum(1 for o in self.observations if o.classification == "flip") / self.n

    @property
    def substantive_rate(self) -> float:
        if self.n == 0:
            return 0.0
        return sum(1 for o in self.observations if o.classification == "substantive") / self.n


# Threshold below which a followup body is considered a "disengaged
# reaffirmation" — i.e., the elder noticed the peer question but did not
# engage with it substantively. Chosen conservatively; fires only on
# very short replies (< 300 chars = roughly 50 words of body beyond the
# tag).
_DISENGAGED_BODY_CHAR_THRESHOLD = 300


def analyse_latching(debate: Debate) -> LatchingReport:
    """Find every `CONVERGED: yes` → peer-question → response triple and
    classify the response.

    Classification rules:
    - **flip**: the elder's followup round has `agreed=False`. The peer
      question dislodged convergence.
    - **disengaged_reaffirm**: `agreed=True` in the followup round AND the
      body is under the character threshold. Elder noticed the question
      but replied with a one-liner reaffirmation.
    - **substantive**: `agreed=True` in the followup round AND body
      exceeds the threshold. Elder actually re-engaged.
    """
    observations: list[LatchingObservation] = []

    for i, round_n in enumerate(debate.rounds):
        for turn in round_n.turns:
            if turn.answer.agreed is not True:
                continue
            # This elder said CONVERGED: yes. Look for peer questions
            # directed at it in this same round's peer turns (because
            # questions are asked IN the round the elder will respond TO
            # in the next round).
            for peer_turn in round_n.turns:
                if peer_turn.elder == turn.elder:
                    continue
                for q in peer_turn.questions:
                    if q.to_elder != turn.elder:
                        continue
                    # Find the followup round where this elder responds.
                    if i + 1 >= len(debate.rounds):
                        continue
                    followup = debate.rounds[i + 1]
                    followup_turn = next(
                        (t for t in followup.turns if t.elder == turn.elder),
                        None,
                    )
                    if followup_turn is None:
                        continue
                    body_len = len((followup_turn.answer.text or "").strip())
                    if followup_turn.answer.agreed is False:
                        classification = "flip"
                    elif (
                        followup_turn.answer.agreed is True
                        and body_len < _DISENGAGED_BODY_CHAR_THRESHOLD
                    ):
                        classification = "disengaged_reaffirm"
                    else:
                        classification = "substantive"

                    observations.append(
                        LatchingObservation(
                            elder=turn.elder,
                            converged_round=round_n.number,
                            peer_asker=q.from_elder,
                            question_text=q.text,
                            followup_round=followup.number,
                            classification=classification,
                            followup_body_chars=body_len,
                        )
                    )

    return LatchingReport(observations=observations)


@dataclass(frozen=True)
class RoundDelta:
    """Semantic-ish delta between an elder's turn in round N and round N-1.

    Uses character-level SequenceMatcher similarity as a cheap proxy for
    "did anything substantive change?". Higher similarity → more churn,
    less new information. A similarity of 0.95+ is a strong signal of a
    near-paraphrase round.
    """

    elder: ElderId
    round_number: int
    similarity: float
    is_low_delta: bool


@dataclass(frozen=True)
class LowDeltaReport:
    deltas: list[RoundDelta]

    @property
    def n(self) -> int:
        return len(self.deltas)

    @property
    def low_delta_rate(self) -> float:
        if self.n == 0:
            return 0.0
        return sum(1 for d in self.deltas if d.is_low_delta) / self.n


_LOW_DELTA_SIMILARITY_THRESHOLD = 0.92


def analyse_low_delta_rounds(debate: Debate) -> LowDeltaReport:
    """Compute per-elder, per-round similarity to the previous round's turn.

    Rounds where similarity exceeds the threshold indicate the elder is
    repeating themselves (low-progress rounds). Used to surface "wasted"
    iteration and inform stopping criteria.
    """
    deltas: list[RoundDelta] = []
    # Build a per-elder history of turn texts across rounds.
    for round_idx, rnd in enumerate(debate.rounds):
        if round_idx == 0:
            continue  # R1 has no previous round to compare against
        prev_round = debate.rounds[round_idx - 1]
        for turn in rnd.turns:
            prev_turn = next((t for t in prev_round.turns if t.elder == turn.elder), None)
            if prev_turn is None:
                continue
            curr_text = (turn.answer.text or "").strip()
            prev_text = (prev_turn.answer.text or "").strip()
            if not curr_text or not prev_text:
                continue
            similarity = SequenceMatcher(None, prev_text, curr_text).ratio()
            deltas.append(
                RoundDelta(
                    elder=turn.elder,
                    round_number=rnd.number,
                    similarity=similarity,
                    is_low_delta=similarity >= _LOW_DELTA_SIMILARITY_THRESHOLD,
                )
            )
    return LowDeltaReport(deltas=deltas)
