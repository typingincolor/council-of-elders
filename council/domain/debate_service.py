from __future__ import annotations

import asyncio
from dataclasses import dataclass

from council.domain.convergence import ConvergencePolicy
from council.domain.events import (
    RoundCompleted,
    SynthesisCompleted,
    TurnCompleted,
    TurnFailed,
    TurnStarted,
)
from council.domain.models import (
    Debate,
    ElderAnswer,
    ElderError,
    ElderId,
    Round,
    Turn,
)
from council.domain.ports import Clock, ElderPort, EventBus, TranscriptStore
from council.domain.prompting import PromptBuilder


@dataclass
class DebateService:
    elders: dict[ElderId, ElderPort]
    store: TranscriptStore
    clock: Clock
    bus: EventBus
    prompt_builder: PromptBuilder = PromptBuilder()
    convergence: ConvergencePolicy = ConvergencePolicy()

    async def run_round(self, debate: Debate) -> Round:
        round_num = len(debate.rounds) + 1

        async def _ask(elder_id: ElderId) -> Turn:
            port = self.elders[elder_id]
            prompt = self.prompt_builder.build(debate, elder_id, round_num)
            await self.bus.publish(TurnStarted(elder=elder_id, round_number=round_num))
            try:
                raw = await port.ask(prompt)
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

            cleaned, agreed = self.convergence.parse(raw)
            ans = ElderAnswer(
                elder=elder_id,
                text=cleaned,
                error=None,
                agreed=agreed,
                created_at=self.clock.now(),
            )
            await self.bus.publish(
                TurnCompleted(elder=elder_id, round_number=round_num, answer=ans)
            )
            return Turn(elder=elder_id, answer=ans)

        turns = await asyncio.gather(*(_ask(eid) for eid in self.elders.keys()))
        r = Round(number=round_num, turns=list(turns))
        debate.rounds.append(r)
        self.store.save(debate)
        await self.bus.publish(RoundCompleted(round=r))
        return r

    async def synthesize(self, debate: Debate, by: ElderId) -> ElderAnswer:
        port = self.elders[by]
        prompt = self.prompt_builder.build_synthesis(debate, by=by)
        try:
            raw = await port.ask(prompt)
            ans = ElderAnswer(
                elder=by,
                text=raw.strip(),
                error=None,
                agreed=None,
                created_at=self.clock.now(),
            )
        except Exception as ex:
            err = ElderError(elder=by, kind="nonzero_exit", detail=repr(ex))
            ans = self._error_answer(by, err)
        debate.synthesis = ans
        debate.status = "synthesized"
        self.store.save(debate)
        await self.bus.publish(SynthesisCompleted(answer=ans))
        return ans

    def _error_answer(self, elder_id: ElderId, err: ElderError) -> ElderAnswer:
        return ElderAnswer(
            elder=elder_id,
            text=None,
            error=err,
            agreed=None,
            created_at=self.clock.now(),
        )
