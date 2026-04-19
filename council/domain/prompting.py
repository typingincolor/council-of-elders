from __future__ import annotations

from council.domain.models import Debate, ElderId

_ELDER_LABEL: dict[ElderId, str] = {
    "claude": "Claude",
    "gemini": "Gemini",
    "chatgpt": "ChatGPT",
}


class PromptBuilder:
    """Builds the content of user/system messages for a phased conversation.

    These methods produce raw strings; DebateService packages them into
    Message tuples and accumulates the per-elder conversation. The elder
    remembers its own prior turns natively (via conversation history), so
    per-round user messages do NOT re-stuff "your previous answer".
    """

    # ---- system + per-phase user-message builders -----------------------

    def build_system_message(self, debate: Debate, elder: ElderId) -> str:
        lines: list[str] = []
        persona = debate.pack.personas.get(elder)
        if persona:
            lines.append(persona.strip())
        if debate.pack.shared_context:
            lines.append(debate.pack.shared_context.strip())
        return "\n\n".join(lines)

    def build_round_1_user(self, debate: Debate) -> str:
        return (
            f"Question: {debate.prompt}\n\n"
            "Give your initial take. Do not tag convergence or ask questions — "
            "this is a silent initial round before you see the other advisors."
        )

    def build_round_2_user(self, debate: Debate, elder: ElderId) -> str:
        parts: list[str] = []
        others = self._other_advisors_section(debate, elder, round_num=2)
        if others:
            parts.append(others)
        user_section = self._user_messages_section(debate)
        if user_section:
            parts.append(user_section)
        parts.append(
            "You have now seen the other advisors. This is the cross-examination round.\n\n"
            "You MUST end your reply with EXACTLY ONE question of EXACTLY ONE peer, "
            "formatted as:\n\n"
            "QUESTIONS:\n"
            "@<peer> your question here\n\n"
            "Where <peer> is one of: @claude, @gemini, @chatgpt (but not yourself).\n"
            "Do NOT emit a CONVERGED tag; convergence is not yet possible."
        )
        return "\n\n".join(parts)

    def build_round_n_user(self, debate: Debate, elder: ElderId, round_num: int) -> str:
        parts: list[str] = []
        others = self._other_advisors_section(debate, elder, round_num=round_num)
        if others:
            parts.append(others)
        user_section = self._user_messages_section(debate)
        if user_section:
            parts.append(user_section)
        directed = self._directed_questions_section(debate, elder, round_num)
        if directed:
            parts.append(directed)
        peer_qs = self._other_questions_section(debate, elder, round_num)
        if peer_qs:
            parts.append(peer_qs)
        parts.append(
            "End your reply with EXACTLY ONE of:\n\n"
            "(a) CONVERGED: yes — if you would not change your position after everything said.\n\n"
            "(b) CONVERGED: no, followed immediately by a QUESTIONS: block:\n\n"
            "    QUESTIONS:\n"
            "    @<peer> your probe here\n\n"
            "If you emit CONVERGED: no, you MUST ask exactly one question of one peer."
        )
        return "\n\n".join(parts)

    def build_retry_reminder(self, violation_detail: str) -> str:
        return (
            "Your previous reply did not follow the required format. "
            f"{violation_detail} "
            "Re-send your answer with the correct structure."
        )

    def build_synthesis(self, debate: Debate, by: ElderId) -> str:
        parts: list[str] = []
        header = self.build_system_message(debate, by)
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

    # ---- private helpers (reused across phases) -------------------------

    def _other_advisors_section(self, debate: Debate, elder: ElderId, round_num: int) -> str:
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

    def _directed_questions_section(self, debate: Debate, elder: ElderId, round_num: int) -> str:
        prior = debate.rounds[round_num - 2]
        directed: list[str] = []
        for t in prior.turns:
            for q in t.questions:
                if q.to_elder == elder:
                    directed.append(f'- From {_ELDER_LABEL[q.from_elder]}: "{q.text}"')
        if not directed:
            return ""
        return "Questions directed at you from the previous round:\n" + "\n".join(directed)

    def _other_questions_section(self, debate: Debate, elder: ElderId, round_num: int) -> str:
        prior = debate.rounds[round_num - 2]
        others: list[str] = []
        for t in prior.turns:
            for q in t.questions:
                if q.to_elder == elder:
                    continue
                others.append(
                    f'- [{_ELDER_LABEL[q.from_elder]} to {_ELDER_LABEL[q.to_elder]}]: "{q.text}"'
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
