from __future__ import annotations

from council.domain.models import Debate, ElderId, Round

_CONVERGED_INSTRUCTION = (
    "End your reply with exactly one of:\n"
    "CONVERGED: yes\n"
    "CONVERGED: no\n\n"
    "(Use CONVERGED: yes only if you would not change your answer after seeing "
    "what other advisors say.)"
)

_QUESTIONS_INSTRUCTION = (
    "If you have questions for another advisor, optionally include them "
    "BEFORE the CONVERGED line, as a block like this:\n\n"
    "QUESTIONS:\n"
    "@gemini your question here\n"
    "@chatgpt another question\n"
)

_ELDER_LABEL: dict[ElderId, str] = {
    "claude": "Claude",
    "gemini": "Gemini",
    "chatgpt": "ChatGPT",
}


class PromptBuilder:
    def build(self, debate: Debate, elder: ElderId, round_num: int) -> str:
        parts: list[str] = []
        header = self._header(debate, elder)
        if header:
            parts.append(header)
        parts.append(f"Question: {debate.prompt}")

        if round_num == 1:
            parts.append("Answer the question.")
            parts.append(_QUESTIONS_INSTRUCTION)
            parts.append(_CONVERGED_INSTRUCTION)
            return "\n\n".join(parts)

        # Round 2+
        own_prev = self._own_previous_answer(debate, elder, round_num)
        if own_prev is not None:
            parts.append(f"Your previous answer:\n{own_prev}")

        others = self._other_advisors_section(debate, elder, round_num)
        if others:
            parts.append(others)

        user_section = self._user_messages_section(debate)
        if user_section:
            parts.append(user_section)

        directed = self._directed_questions_section(debate, elder, round_num)
        if directed:
            parts.append(directed)

        other_qs = self._other_questions_section(debate, elder, round_num)
        if other_qs:
            parts.append(other_qs)

        parts.append(
            "You may revise your answer if their arguments change your view, "
            "or stand by it."
        )
        parts.append(_QUESTIONS_INSTRUCTION)
        parts.append(_CONVERGED_INSTRUCTION)
        return "\n\n".join(parts)

    def build_synthesis(self, debate: Debate, by: ElderId) -> str:
        parts: list[str] = []
        header = self._header(debate, by)
        if header:
            parts.append(header)
        parts.append(f"Original question: {debate.prompt}")
        parts.append(self._all_rounds_section(debate))
        parts.append(
            "You have seen every advisor's contribution across every round. "
            "Produce the final synthesised answer that best represents the "
            "consensus (or, where no consensus exists, your best judgment "
            "informed by the debate). Do not append a convergence tag."
        )
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    def _header(self, debate: Debate, elder: ElderId) -> str:
        lines: list[str] = []
        persona = debate.pack.personas.get(elder)
        if persona:
            lines.append(persona.strip())
        if debate.pack.shared_context:
            lines.append(debate.pack.shared_context.strip())
        return "\n\n".join(lines)

    def _own_previous_answer(
        self, debate: Debate, elder: ElderId, round_num: int
    ) -> str | None:
        prior = debate.rounds[round_num - 2]
        for t in prior.turns:
            if t.elder == elder and t.answer.text:
                return t.answer.text
        return None

    def _other_advisors_section(
        self, debate: Debate, elder: ElderId, round_num: int
    ) -> str:
        prior = debate.rounds[round_num - 2]
        lines = ["Other advisors said:"]
        for t in prior.turns:
            if t.elder == elder:
                continue
            if not t.answer.text:
                continue
            lines.append(f"[{_ELDER_LABEL[t.elder]}] {t.answer.text}")
        if len(lines) == 1:
            return ""
        return "\n".join(lines)

    def _user_messages_section(self, debate: Debate) -> str:
        if not debate.user_messages:
            return ""
        lines = ["You (the asker) said:"]
        for m in debate.user_messages:
            lines.append(f'After round {m.after_round}: "{m.text}"')
        return "\n".join(lines)

    def _directed_questions_section(
        self, debate: Debate, elder: ElderId, round_num: int
    ) -> str:
        prior = debate.rounds[round_num - 2]
        directed: list[str] = []
        for t in prior.turns:
            for q in t.questions:
                if q.to_elder == elder:
                    directed.append(
                        f'- From {_ELDER_LABEL[q.from_elder]}: "{q.text}"'
                    )
        if not directed:
            return ""
        return "Questions directed at you from the previous round:\n" + "\n".join(
            directed
        )

    def _other_questions_section(
        self, debate: Debate, elder: ElderId, round_num: int
    ) -> str:
        prior = debate.rounds[round_num - 2]
        others: list[str] = []
        for t in prior.turns:
            for q in t.questions:
                if q.to_elder == elder:
                    continue
                others.append(
                    f'- [{_ELDER_LABEL[q.from_elder]} to '
                    f'{_ELDER_LABEL[q.to_elder]}]: "{q.text}"'
                )
        if not others:
            return ""
        return "Other questions raised between advisors:\n" + "\n".join(others)

    def _all_rounds_section(self, debate: Debate) -> str:
        chunks: list[str] = []
        for r in debate.rounds:
            chunks.append(f"--- Round {r.number} ---")
            for t in r.turns:
                if not t.answer.text:
                    continue
                chunks.append(f"[{_ELDER_LABEL[t.elder]}] {t.answer.text}")
        return "\n".join(chunks)
