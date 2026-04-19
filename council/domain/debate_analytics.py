"""Transcript analytics for evidence-based design decisions.

Reads saved debates and computes scorers that quantify the failure
modes the design-level meta-debate (`44e04e1e`) identified as priorities
to measure:

- **Convergence latching** — when an elder says `CONVERGED: yes` in round N
  and a peer directs a question at them in round N+1, does the elder
  substantively re-engage, reaffirm with a disengaged one-liner, or flip?
  Pure structural — no LLM calls.

- **Low-delta rounds** — lightweight heuristic for rounds that added no
  new information. SequenceMatcher on consecutive turns.

- **Task-fidelity (drift) via LLM rubric judge** — a small judge model
  scores the synthesised answer against the user's original question on
  shape-fit (0-3) and content-fit (0-3), plus a drift_flag. Uses a
  separate judge port (typically a cheap / free model via OpenRouter)
  so it doesn't burn flagship budget. Async.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from council.domain.models import Debate, ElderId, Message
from council.domain.ports import ElderPort


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


# ---- LLM-rubric drift judge ------------------------------------------


@dataclass(frozen=True)
class DriftObservation:
    debate_id: str
    shape_fit: int  # 0-3, how well the synthesis matches the requested form
    content_fit: int  # 0-3, how well it answers the question asked
    drift_flag: bool  # True = the debate drifted to a different question
    reason: str  # judge's short justification
    raw: str  # unparsed judge reply, for diagnostics


_DRIFT_RUBRIC_PROMPT = """You are a neutral judge scoring a debate output for task fidelity. A user asked a question; a group of advisors debated; a final synthesised answer was produced. Your job: did the synthesis actually answer what the user asked, in the SHAPE they asked for?

User's original question:
<<<
{question}
>>>

Final synthesised answer:
<<<
{synthesis}
>>>

Score on this rubric, then emit EXACTLY these four lines, nothing else. No preamble, no markdown, no explanation before the lines.

shape_fit: N  (0 = wrong shape; 1 = partial shape match; 2 = mostly correct shape; 3 = exact requested shape)
content_fit: N  (0 = did not answer the question; 1 = partial answer; 2 = substantive answer with minor gaps; 3 = complete faithful answer)
drift_flag: yes  (if the debate drifted into an adjacent but different question)
drift_flag: no  (if the synthesis answers the question that was actually asked)
reason: ONE short sentence explaining the scores, citing the specific shape/content mismatch if any.

Pick exactly one of the two drift_flag lines, not both."""


_SHAPE_FIT_RE = re.compile(r"^\s*shape_fit\s*:\s*([0-3])", re.MULTILINE | re.IGNORECASE)
_CONTENT_FIT_RE = re.compile(r"^\s*content_fit\s*:\s*([0-3])", re.MULTILINE | re.IGNORECASE)
_DRIFT_FLAG_RE = re.compile(r"^\s*drift_flag\s*:\s*(yes|no)", re.MULTILINE | re.IGNORECASE)
_REASON_RE = re.compile(r"^\s*reason\s*:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE)


def _parse_drift_verdict(raw: str, debate_id: str) -> DriftObservation:
    """Parse the judge's response into a structured observation.

    Tolerant of extra whitespace, markdown fencing, minor formatting
    deviations. Missing fields default to a conservative "unsure" reading
    (shape=content=2, drift_flag=False) so a malformed response doesn't
    silently flip to a false-positive drift.
    """
    # Strip markdown fences if the model added them.
    cleaned = re.sub(r"^```[a-z]*\n?|\n?```$", "", raw.strip(), flags=re.MULTILINE)

    shape_m = _SHAPE_FIT_RE.search(cleaned)
    content_m = _CONTENT_FIT_RE.search(cleaned)
    drift_m = _DRIFT_FLAG_RE.search(cleaned)
    reason_m = _REASON_RE.search(cleaned)

    shape_fit = int(shape_m.group(1)) if shape_m else 2
    content_fit = int(content_m.group(1)) if content_m else 2
    drift_flag = drift_m.group(1).lower() == "yes" if drift_m else False
    reason = reason_m.group(1).strip() if reason_m else "(judge response did not include a reason)"

    return DriftObservation(
        debate_id=debate_id,
        shape_fit=shape_fit,
        content_fit=content_fit,
        drift_flag=drift_flag,
        reason=reason,
        raw=raw,
    )


async def analyse_drift(debate: Debate, judge_port: ElderPort) -> DriftObservation | None:
    """Ask a small judge model to rate synthesis fidelity to the user's ask.

    Returns None if the debate has no synthesis yet (nothing to judge).
    Judge output is parsed tolerantly; malformed replies default to a
    neutral reading.
    """
    if debate.synthesis is None or not (debate.synthesis.text or "").strip():
        return None

    prompt = _DRIFT_RUBRIC_PROMPT.format(
        question=debate.prompt.strip(),
        synthesis=debate.synthesis.text.strip(),
    )
    raw = await judge_port.ask([Message("user", prompt)])
    return _parse_drift_verdict(raw, debate.id)
