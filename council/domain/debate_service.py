from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from council.domain.convergence import ConvergencePolicy
from council.domain.events import (
    RoundCompleted,
    SynthesisCompleted,
    TurnCompleted,
    TurnFailed,
    TurnStarted,
    UserMessageReceived,
)
from council.domain.models import (
    Debate,
    ElderAnswer,
    ElderError,
    ElderId,
    Message,
    Round,
    Turn,
    UserMessage,
)
from council.domain.ports import Clock, ElderPort, EventBus, TranscriptStore
from council.domain.prompting import PromptBuilder
from council.domain.questions import QuestionParser
from council.domain.reporting import ReportBuilder
from council.domain.rules import DebateRules, DefaultRules, Violation
from council.domain.synthesis_validation import SynthesisValidator, SynthesisViolation

log = logging.getLogger(__name__)


@dataclass
class DebateService:
    elders: dict[ElderId, ElderPort]
    store: TranscriptStore
    clock: Clock
    bus: EventBus
    rules: DebateRules = field(default_factory=DefaultRules)
    prompt_builder: PromptBuilder = field(default_factory=PromptBuilder)
    convergence: ConvergencePolicy = field(default_factory=ConvergencePolicy)
    question_parser: QuestionParser = field(default_factory=QuestionParser)
    report_builder: ReportBuilder = field(default_factory=ReportBuilder)
    synthesis_validator: SynthesisValidator = field(default_factory=SynthesisValidator)
    conversations: dict[ElderId, list[Message]] = field(default_factory=dict)

    async def run_round(self, debate: Debate) -> Round:
        round_num = len(debate.rounds) + 1

        async def _ask(elder_id: ElderId) -> Turn:
            port = self.elders[elder_id]
            conv = self.conversations.setdefault(elder_id, [])

            # Append the next user message (and system on first round).
            if not conv:
                system_text = self.rules.system_message(debate, elder_id)
                if system_text:
                    conv.append(Message("system", system_text))
            conv.append(Message("user", self.rules.user_message(debate, elder_id, round_num)))

            await self.bus.publish(TurnStarted(elder=elder_id, round_number=round_num))

            try:
                raw = await port.ask(conv)
            except asyncio.TimeoutError:
                err = ElderError(elder=elder_id, kind="timeout", detail="")
                ans = self._error_answer(elder_id, err)
                await self.bus.publish(
                    TurnFailed(elder=elder_id, round_number=round_num, error=err)
                )
                return Turn(elder=elder_id, answer=ans)
            except Exception as ex:
                kind = getattr(ex, "kind", "nonzero_exit")
                detail = getattr(ex, "detail", repr(ex))
                err = ElderError(elder=elder_id, kind=kind, detail=detail)
                ans = self._error_answer(elder_id, err)
                await self.bus.publish(
                    TurnFailed(elder=elder_id, round_number=round_num, error=err)
                )
                return Turn(elder=elder_id, answer=ans)

            # Parse QUESTIONS first to strip the trailing block, then look
            # for the CONVERGED tag on what's left. The R3+ prompt tells the
            # model to emit CONVERGED BEFORE the QUESTIONS block, so running
            # the convergence policy on raw text would miss the tag (the
            # QUESTIONS lines would be the tail).
            cleaned_qs, questions = self.question_parser.parse(
                raw, from_elder=elder_id, round_number=round_num
            )
            cleaned2, agreed = self.convergence.parse(cleaned_qs)
            result = self.rules.validate(
                agreed=agreed,
                questions=questions,
                round_num=round_num,
                from_elder=elder_id,
            )

            final_raw = raw

            # Retry once on contract violation.
            if isinstance(result, Violation):
                conv.append(Message("assistant", raw))
                conv.append(Message("user", self.rules.retry_reminder(result)))
                try:
                    raw2 = await port.ask(conv)
                except asyncio.TimeoutError:
                    err = ElderError(elder=elder_id, kind="timeout", detail="")
                    ans = self._error_answer(elder_id, err)
                    await self.bus.publish(
                        TurnFailed(elder=elder_id, round_number=round_num, error=err)
                    )
                    return Turn(elder=elder_id, answer=ans)
                except Exception as ex:
                    kind = getattr(ex, "kind", "nonzero_exit")
                    detail = getattr(ex, "detail", repr(ex))
                    err = ElderError(elder=elder_id, kind=kind, detail=detail)
                    ans = self._error_answer(elder_id, err)
                    await self.bus.publish(
                        TurnFailed(elder=elder_id, round_number=round_num, error=err)
                    )
                    return Turn(elder=elder_id, answer=ans)
                cleaned_qs, questions = self.question_parser.parse(
                    raw2, from_elder=elder_id, round_number=round_num
                )
                cleaned2, agreed = self.convergence.parse(cleaned_qs)
                final_raw = raw2
                # Accept whatever; one retry ceiling. Log if still invalid.
                post_result = self.rules.validate(
                    agreed=agreed,
                    questions=questions,
                    round_num=round_num,
                    from_elder=elder_id,
                )
                if isinstance(post_result, Violation):
                    log.warning(
                        "Elder %s round %s still violates contract after retry: %s",
                        elder_id,
                        round_num,
                        post_result.reason,
                    )

            # Phase-specific drop-with-warn cleanup (DefaultRules conventions).
            if round_num == 1:
                if agreed is not None or questions:
                    log.warning(
                        "Elder %s round 1 emitted unexpected convergence/questions; dropping.",
                        elder_id,
                    )
                agreed = None
                questions = ()
            elif round_num >= 3 and agreed is True and questions:
                log.warning(
                    "Elder %s round %s emitted CONVERGED: yes with questions; dropping questions.",
                    elder_id,
                    round_num,
                )
                questions = ()

            # Record assistant reply in the conversation.
            conv.append(Message("assistant", final_raw))

            ans = ElderAnswer(
                elder=elder_id,
                text=cleaned2,
                error=None,
                agreed=agreed,
                created_at=self.clock.now(),
            )
            await self.bus.publish(
                TurnCompleted(
                    elder=elder_id,
                    round_number=round_num,
                    answer=ans,
                    questions=questions,
                )
            )
            return Turn(elder=elder_id, answer=ans, questions=questions)

        turns = await asyncio.gather(*(_ask(eid) for eid in self.elders.keys()))
        r = Round(number=round_num, turns=list(turns))
        debate.rounds.append(r)
        self.store.save(debate)
        await self.bus.publish(RoundCompleted(round=r))
        return r

    async def synthesize(
        self,
        debate: Debate,
        by: ElderId,
        *,
        synthesis_prompt_override: str | None = None,
    ) -> ElderAnswer:
        """Run the synthesis pass. ``synthesis_prompt_override`` lets a
        caller supply an alternative synthesis prompt (e.g. for a
        format ablation); defaults to the PromptBuilder's
        Answer/Why/Disagreements structure.
        """
        port = self.elders[by]
        prompt = synthesis_prompt_override or self.prompt_builder.build_synthesis(debate, by=by)
        try:
            raw = await port.ask([Message("user", prompt)])

            # Post-generation structural validation. Belt-and-braces against
            # decoding pathologies the prompt alone can't fully solve
            # (CoT-loop leakage on fast-tier models, draft-label emission,
            # etc.). One-retry ceiling; accept whatever comes back on the
            # retry, same policy as the turn-contract retry.
            check = self.synthesis_validator.validate(raw)
            if isinstance(check, SynthesisViolation):
                log.warning(
                    "Synthesis structural violation (%s): %s. Retrying once.",
                    check.reason,
                    check.detail,
                )
                retry_prompt = (
                    f"Your previous reply had a structural problem: {check.detail} "
                    "Re-send the synthesis with the correct structure. "
                    "Begin immediately with the first word of the answer. "
                    "No preamble, no headings, no draft labels, no mentions "
                    "of the debate or advisors, no CONVERGED tag."
                )
                raw = await port.ask(
                    [
                        Message("user", prompt),
                        Message("assistant", raw),
                        Message("user", retry_prompt),
                    ]
                )
                post = self.synthesis_validator.validate(raw)
                if isinstance(post, SynthesisViolation):
                    log.warning(
                        "Synthesis still violates structure after retry (%s); "
                        "accepting best-effort.",
                        post.reason,
                    )

            ans = ElderAnswer(
                elder=by,
                text=raw.strip(),
                error=None,
                agreed=None,
                created_at=self.clock.now(),
            )
        except Exception as ex:
            kind = getattr(ex, "kind", "nonzero_exit")
            detail = getattr(ex, "detail", repr(ex))
            err = ElderError(elder=by, kind=kind, detail=detail)
            ans = self._error_answer(by, err)
        debate.synthesis = ans
        debate.status = "synthesized"
        self.store.save(debate)
        await self.bus.publish(SynthesisCompleted(answer=ans))
        return ans

    async def generate_report(
        self,
        debate: Debate,
        *,
        by: ElderId,
        synthesis_risk_note: str | None = None,
    ) -> str:
        """Produce a markdown debate report (metadata + narrative).

        Called after `synthesize`. Appends a narrative-request turn to the
        synthesiser's conversation and asks for a ~200-word report on how
        the debate unfolded. ``synthesis_risk_note`` is forwarded to the
        report builder to flag rosters where synthesis historically
        underperforms best-R1 (low/medium diversity).
        """
        if debate.synthesis is None:
            raise ValueError("generate_report requires a prior successful synthesize()")

        port = self.elders[by]
        narrative_prompt = self.report_builder.build_narrative_prompt(debate, debate.synthesis)

        # Use a one-shot conversation here. The synthesiser's per-elder
        # conversation in `self.conversations` has the full debate history;
        # we could reuse it, but reporting is distinct from the debate
        # turn-taking, and keeping it single-shot keeps the semantics clean
        # (the report doesn't belong in the elder's debate memory).
        conversation = [
            Message("user", self.prompt_builder.build_synthesis(debate, by=by)),
            Message("assistant", debate.synthesis.text or ""),
            Message("user", narrative_prompt),
        ]
        try:
            narrative = await port.ask(conversation)
        except Exception as ex:  # pragma: no cover - exception path bubbles up
            log.warning(
                "Report narrative generation failed for debate %s: %s",
                debate.id,
                ex,
            )
            narrative = "_(narrative unavailable: the reporter elder failed to respond.)_"

        return self.report_builder.assemble_report_markdown(
            debate,
            debate.synthesis,
            narrative,
            synthesiser=by,
            synthesis_risk_note=synthesis_risk_note,
        )

    async def add_user_message(self, debate: Debate, text: str) -> UserMessage:
        msg = UserMessage(
            text=text.strip(),
            after_round=len(debate.rounds),
            created_at=self.clock.now(),
        )
        debate.user_messages.append(msg)
        self.store.save(debate)
        await self.bus.publish(UserMessageReceived(message=msg))
        return msg

    def _error_answer(self, elder_id: ElderId, err: ElderError) -> ElderAnswer:
        return ElderAnswer(
            elder=elder_id,
            text=None,
            error=err,
            agreed=None,
            created_at=self.clock.now(),
        )
