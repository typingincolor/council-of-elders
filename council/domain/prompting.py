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
        # Rewrite origin: produced by the council meta-debate 46c48a09.
        # Fixes: empty-body permissiveness, introspective convergence
        # criterion, tag-mimicry, stray-header shadowing, ordering
        # ambiguity, indent mimicry, positional ambiguity of the tag,
        # underspecified question format.
        parts.append(
            "Write a substantive reply first. Never reply with only a tag, "
            "and do not use the exact strings `QUESTIONS:` or `CONVERGED:` "
            "anywhere in your reasoning body — reserve those headers for the "
            "closing block described below.\n\n"
            "Then close your reply using EXACTLY ONE of these two formats, "
            "as the final lines of your output, with no indentation, bullets, "
            "code fences, or text after them.\n\n"
            "If you do not need any further answer from a peer to finalize "
            "your position, close with a single flush-left line:\n\n"
            "CONVERGED: yes\n\n"
            "If you are not yet settled, close with three flush-left lines in "
            "this exact order:\n\n"
            "CONVERGED: no\n"
            "QUESTIONS:\n"
            "@<peer> <one direct, specific question>\n\n"
            "Rules:\n"
            "- If `CONVERGED: no`, ask exactly one question addressed to "
            "exactly one peer by name with a leading `@`, on a single line.\n"
            "- If `CONVERGED: yes`, include no question and no `QUESTIONS:` "
            "header.\n"
            "- The closing block must be the absolute final lines of your "
            "reply. Do not add sign-offs, commentary, or blank-line padding "
            "after it.\n"
            "- Use this exact capitalization and spelling: `CONVERGED: yes`, "
            "`CONVERGED: no`, `QUESTIONS:`."
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
        parts.append(f"The user's original question was:\n\n{debate.prompt}")
        parts.append(self._all_rounds_section(debate))
        # Rewrite origin: produced by the council meta-debate 5142e6fc.
        # Fixes: aspirational-form wording replaced with pragmatic-brevity
        # operationalisation; transcript-length mimicry severed explicitly;
        # authorship-bias rule added ("synthesize, don't select"); draft-label
        # ban generalised from token-blacklist to category (process
        # scaffolding of any kind); first-token anchor added; separation-of-
        # concerns note ("a separate downstream step audits the debate").
        parts.append(
            "You have seen every advisor across every round. Write the final "
            "answer the user receives. A separate downstream step audits the "
            "debate — that is not your job. Your job is the clean answer.\n\n"
            "**Form and length.** Match the shape and the brevity the user's "
            'request implies in normal usage. "One sentence" means one short '
            'sentence, not a 30-word multi-clause one. "Headline," "slogan," '
            '"tagline," "one-liner," "tweet," "short answer" all mean '
            "genuinely punchy, not merely technically compliant. If the user "
            "gave an example, match its register and length. If the form is "
            "unspecified, default to the shortest response that fully "
            "answers. Do not inherit length or structure from the advisors "
            "when it conflicts with the user's ask — calibrate to the user, "
            "not the transcript. Add no structure beyond what the user "
            "requested (no bullets, headings, or sections unless asked).\n\n"
            "**Synthesize, do not select.** Do not copy any single advisor's "
            "wording wholesale when others contributed. Take the strongest "
            "formulation of each component from whichever advisor expressed "
            "it best, and write it in your own voice. Where advisors "
            "disagreed, decide based on the strongest argument in the "
            "transcript — not recency, confidence, or majority — and output "
            "only your decision.\n\n"
            "**Output discipline.** Output only the answer itself. No "
            "preamble, sign-off, framing sentence, section headings, labels, "
            "markdown scaffolding, tags, or meta-commentary. Do not mention "
            "the debate, the advisors, agreement, disagreement, or your "
            "reasoning. Do not emit process scaffolding of any kind — no "
            "draft markers, phase headings, or iterative-refinement "
            'structure (e.g. "Goal:", "Approach:", "Synthesis:", "Draft:", '
            '"Refined:", "**Defining X**", "Step 1:"). Do not append a '
            "CONVERGED tag.\n\n"
            "Begin your response with the first word of the answer itself."
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
