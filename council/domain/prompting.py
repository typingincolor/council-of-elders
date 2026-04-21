from __future__ import annotations

from council.domain.models import Debate, ElderId

_ELDER_LABEL: dict[ElderId, str] = {
    "ada": "Ada",
    "kai": "Kai",
    "mei": "Mei",
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
        # Rewrite origin: council meta-debate 2e1d4cda (bundled with R2).
        # Fixes: "silent"/"initial take" priming brevity; purely negative
        # framing; "do not ask questions" over-suppressing rhetorical
        # interrogatives in reasoning; "convergence" word priming the
        # CONVERGED token; no substantive-body requirement; no explanation
        # of why depth matters. Also aligned with R3+ patterns: first-word
        # anchor, scaffolding ban, reserved literal tag strings.
        return (
            f"Question: {debate.prompt}\n\n"
            "Answer the question fully and directly, using your normal level "
            "of reasoning and detail. This is the independent first round, "
            "before you see the other advisors, so give your real substantive "
            "answer rather than a sketch, preview, or hedge. Your answer "
            "will be shown to the other advisors next round for cross-"
            "examination, so give them something of substance to engage "
            "with.\n\n"
            "Begin with the first word of your answer. Do not include "
            "preamble, sign-offs, meta-commentary, section headings, draft "
            "labels, or other process scaffolding of any kind.\n\n"
            "Do not include the literal strings CONVERGED: or QUESTIONS: "
            "anywhere in your reply. Do not address any peer or ask any "
            "peer-directed question in this round. Ordinary interrogative "
            "sentences inside your own reasoning are fine."
        )

    def build_round_2_user(self, debate: Debate, elder: ElderId) -> str:
        parts: list[str] = []
        others = self._other_advisors_section(debate, elder, round_num=2)
        if others:
            parts.append(others)
        user_section = self._user_messages_section(debate)
        if user_section:
            parts.append(user_section)
        # Rewrite origin: council meta-debate 2e1d4cda (bundled with R1).
        # Fixes: <peer> placeholder mimicry; question register not enforced;
        # no body-engagement criterion; self-targeting only caught by
        # validator; re-priming of CONVERGED token; compound-question
        # ambiguity; no "nothing after the block" rule. Aligned with R3+
        # patterns: first-word anchor, scaffolding ban, reserved literal
        # strings in body, flush-left example with exact format.
        parts.append(
            "You have now seen the other advisors' first-round answers. "
            "Respond with substantive analysis that engages at least one "
            "specific load-bearing claim, assumption, or omission in a "
            "peer's answer, then end by asking exactly one direct question "
            "to exactly one peer.\n\n"
            "Begin with the first word of your answer. Do not include "
            "preamble, sign-offs, meta-commentary, section headings, or "
            "other process scaffolding of any kind. Do not include the "
            "literal strings CONVERGED: or QUESTIONS: anywhere in the body "
            "of your reasoning.\n\n"
            "Your reply must end with this exact closing block, flush left, "
            "with exact capitalization, and with nothing after it:\n\n"
            "QUESTIONS:\n"
            "@ada your direct question here\n\n"
            "Replace @ada with exactly one of @ada, @kai, or "
            "@mei, but not yourself. Use the exact lowercase handle "
            "with @, not variants such as Ada:, To Ada —, or "
            "@Ada. Ask exactly one real, direct interrogative sentence "
            'ending in "?", addressed to that one peer, and targeting a '
            "specific load-bearing element of that peer's answer. Do not "
            "give advice phrased as a question, do not ask a rhetorical "
            'question, and do not chain multiple questions with "and also" '
            "or similar. Convergence is not assessed this round; do not "
            "emit any convergence tag."
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

    def build_round_2_silent_revise(self, debate: Debate, elder: ElderId) -> str:
        """Silent-revise R2 prompt: each elder sees the others' R1 answers
        and rewrites their own answer in their own voice, incorporating
        or rejecting the others' points as they judge fit.

        Critical: no peer-directed questions, no QUESTIONS block, no
        CONVERGED tag. This isn't a debate turn — it's a private revision
        step that happens to be informed by what the peers wrote.
        """
        parts: list[str] = []
        others = self._other_advisors_section(debate, elder, round_num=2)
        if others:
            parts.append(others)
        user_section = self._user_messages_section(debate)
        if user_section:
            parts.append(user_section)
        parts.append(
            "You have now read the other advisors' first-round answers. "
            "Re-write your OWN answer to the original question in your own "
            "voice, incorporating any points from the others that sharpen "
            "your thinking and rejecting any that don't. This is a private "
            "revision step, not a response to the others — do not address "
            "them, do not ask them questions, do not argue with them. Think "
            "of it as seeing peer work and then privately deciding whether "
            "and how to revise your own position.\n\n"
            "Begin with the first word of your revised answer. Do not "
            "include preamble, sign-offs, meta-commentary, section "
            "headings, or other process scaffolding.\n\n"
            "Do not include the literal strings CONVERGED:, QUESTIONS:, "
            "or any @advisor handle anywhere in your reply. If the others' "
            "answers didn't change your view, the right response is to "
            "restate your position in its strongest form — not to reply "
            'with "I agree" or "no change".'
        )
        return "\n\n".join(parts)

    def build_synthesis(self, debate: Debate, by: ElderId) -> str:
        parts: list[str] = []
        header = self.build_system_message(debate, by)
        if header:
            parts.append(header)
        parts.append(f"The user's original question was:\n\n{debate.prompt}")
        parts.append(self._all_rounds_section(debate))
        # Rewrite origin: diversity-engine refocus (docs/superpowers/plans/
        # 2026-04-20-diversity-engine-refactor.md). Previous version aimed
        # for a clean single-block answer; this one emits a three-section
        # structure (ANSWER / WHY / DISAGREEMENTS) so the user-facing
        # deliverable can preserve decision-relevant divergence instead
        # of collapsing it. The "synthesize, don't select" discipline and
        # form/length calibration are unchanged — only the output shape.
        parts.append(
            "You have seen every advisor across every round. Write the final "
            "deliverable the user receives.\n\n"
            "**Form and length.** Inside the ANSWER section, match the shape "
            "and brevity the user's request implies in normal usage. \"One "
            'sentence" means one short sentence. "Headline," "slogan," '
            '"tagline," "tweet," "short answer" mean genuinely punchy. If '
            "the user gave an example, match its register and length. If the "
            "form is unspecified, default to the shortest response that fully "
            "answers. Calibrate to the user's ask, not to the transcript "
            "length. Add no structure beyond what the user requested inside "
            "the ANSWER section (no bullets, headings, or sub-sections unless "
            "the user asked).\n\n"
            "**Synthesize, do not select.** Do not copy any single advisor's "
            "wording wholesale when others contributed. Take the strongest "
            "formulation of each component from whichever advisor expressed "
            "it best, and write it in your own voice. Where advisors "
            "disagreed, decide on the strongest argument in the transcript — "
            "not recency, confidence, or majority — and put your decision in "
            "ANSWER. Record the losing position (and why it matters) under "
            "DISAGREEMENTS, not in ANSWER.\n\n"
            "**Output format.** Emit EXACTLY these three labelled sections "
            "in this order, with the labels flush-left in uppercase exactly "
            "as shown. No preamble, no sign-off, no text before ANSWER: or "
            "after the last DISAGREEMENTS line. Do not append a CONVERGED "
            "tag.\n\n"
            "ANSWER:\n"
            "<the user-facing deliverable, calibrated to the user's ask>\n\n"
            "WHY:\n"
            "<1-3 short sentences on the load-bearing reason, in your own "
            "voice — no advisor names>\n\n"
            "DISAGREEMENTS:\n"
            "- <one bullet per DECISION-RELEVANT disagreement between "
            "advisors: a divergence counts only if it would change action, "
            "interpretation, scope, caveats, confidence, or edge-case "
            "handling for the user. Attribute where useful "
            '(e.g. "Ada argued X; Kai argued Y"). Skip stylistic or '
            "framing differences.>\n"
            "- <additional bullets as needed>\n\n"
            "If advisors agreed on every decision-relevant point, write "
            "exactly `(none)` as the only line under DISAGREEMENTS."
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


# Alternative synthesis prompt — free-form, no Answer/Why/Disagreements
# structure. Used by the format ablation to test whether the structured
# output format is the bottleneck. Same "synthesize, don't select" and
# form-calibration disciplines; drops the label scaffolding.
ALT_SYNTHESIS_PROMPT = (
    "You have seen every advisor across every round. Write the final "
    "answer the user receives.\n\n"
    "**Form and length.** Match the shape and brevity the user's request "
    'implies. "One sentence" means one short sentence. "Headline," '
    '"slogan," "tagline," "tweet," "short answer" mean genuinely punchy. '
    "If the user gave an example, match its register and length. If the "
    "form is unspecified, default to the shortest response that fully "
    "answers. Calibrate to the user's ask, not to the transcript length. "
    "Add no structure beyond what the user requested.\n\n"
    "**Synthesize, do not select.** Take the strongest formulation of "
    "each component from whichever advisor expressed it best, and write "
    "it in your own voice. Where advisors disagreed, decide on the "
    "strongest argument and output only your decision.\n\n"
    "**Output discipline.** Output only the answer itself. No preamble, "
    "no sign-off, no labels, no section headings, no meta-commentary, no "
    "mentions of the advisors or the debate. Begin your response with "
    "the first word of the answer."
)


def build_alt_synthesis(debate: Debate, by: ElderId) -> str:
    """Builds the alt free-form synthesis prompt. Mirrors the structure
    of ``PromptBuilder.build_synthesis`` (system header + original
    question + full rounds transcript) but uses ``ALT_SYNTHESIS_PROMPT``
    as the closing instruction instead of the Answer/Why/Disagreements
    scaffolding.
    """
    pb = PromptBuilder()
    parts: list[str] = []
    header = pb.build_system_message(debate, by)
    if header:
        parts.append(header)
    parts.append(f"The user's original question was:\n\n{debate.prompt}")
    parts.append(pb._all_rounds_section(debate))
    parts.append(ALT_SYNTHESIS_PROMPT)
    return "\n\n".join(parts)
