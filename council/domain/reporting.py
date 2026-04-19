"""Debate report generation.

Produces a markdown "debate report" for a completed debate: a deterministic
metadata header (rounds, questions, convergence timeline) plus an
LLM-generated narrative (positions, pivots, concessions).

This module is pure — no I/O, no LLM calls. It builds the text inputs
that DebateService consumes (and the prompt it sends to the elder).
"""

from __future__ import annotations

from council.domain.models import Debate, ElderAnswer, ElderId

_ELDER_LABEL: dict[ElderId, str] = {
    "claude": "Claude",
    "gemini": "Gemini",
    "chatgpt": "ChatGPT",
}


class ReportBuilder:
    def build_metadata_section(self, debate: Debate) -> str:
        """Deterministic metadata: rounds, question list, convergence timeline.

        Emits markdown. No LLM involvement.
        """
        lines: list[str] = ["## Debate metadata", ""]
        lines.append(f"- **Rounds:** {len(debate.rounds)}")
        total_qs = sum(len(t.questions) for r in debate.rounds for t in r.turns)
        lines.append(f"- **Questions asked:** {total_qs}")
        lines.append(f"- **Convergence:** {self._convergence_summary(debate)}")

        if total_qs > 0:
            lines.append("")
            lines.append("### Questions raised during the debate")
            lines.append("")
            for r in debate.rounds:
                for t in r.turns:
                    for q in t.questions:
                        asker = _ELDER_LABEL[q.from_elder]
                        target = _ELDER_LABEL[q.to_elder]
                        lines.append(f'- **R{r.number} {asker} → {target}:** "{q.text}"')

        lines.append("")
        lines.append("### Convergence timeline")
        lines.append("")
        lines.append(self._convergence_table(debate))

        if debate.user_messages:
            lines.append("")
            lines.append("### User messages")
            lines.append("")
            for m in debate.user_messages:
                lines.append(f'- **After R{m.after_round}:** "{m.text}"')

        return "\n".join(lines)

    def build_narrative_prompt(self, debate: Debate, synthesis: ElderAnswer) -> str:
        """The prompt sent to the elder asking for the narrative section.

        The elder has already seen the full debate (conversation history)
        or, for headless / fresh calls, a transcript; the prompt gives it
        one more job after synthesis: describe what happened.
        """
        return (
            "You have just synthesised a council-of-elders debate. Now write a "
            "brief debate report (~200 words, markdown) describing HOW the "
            "debate unfolded — not what the answer is (that's already in the "
            "synthesis). Cover:\n\n"
            "- Each elder's opening position in round 1, in one sentence each.\n"
            "- The key tensions or disagreements that surfaced in round 2 and beyond.\n"
            "- Any notable concessions or shifts in position across rounds.\n"
            "- How convergence evolved — who converged first, what probes remained, "
            "whether dissent was genuine or resolved.\n"
            "- Whether the synthesis represents the group's real consensus or "
            "your best judgment where consensus was incomplete.\n\n"
            'Write in past tense, third-person (e.g. "Claude argued…", "Gemini '
            'conceded…"). Do NOT repeat the synthesised answer; summarise the '
            "process. Start directly with the content — no preamble, no heading."
        )

    def assemble_report_markdown(
        self,
        debate: Debate,
        synthesis: ElderAnswer,
        narrative: str,
        *,
        synthesiser: ElderId,
    ) -> str:
        """Combine everything into the final markdown file content."""
        parts: list[str] = []
        parts.append(f"# Council of Elders — debate `{debate.id}`")
        parts.append("")
        parts.append(f"**Question:** {debate.prompt}")
        parts.append("")
        parts.append(f"**Synthesised by:** {_ELDER_LABEL[synthesiser]}")
        parts.append("")
        parts.append("## Synthesised answer")
        parts.append("")
        parts.append(synthesis.text or "_(no text)_")
        parts.append("")
        parts.append(self.build_metadata_section(debate))
        parts.append("")
        parts.append("## Narrative")
        parts.append("")
        parts.append(narrative.strip())
        parts.append("")
        return "\n".join(parts)

    # ---- helpers --------------------------------------------------------

    def _convergence_summary(self, debate: Debate) -> str:
        for r in debate.rounds:
            if r.converged():
                return f"All three elders converged in round {r.number}."
        return "No full convergence before synthesis."

    def _convergence_table(self, debate: Debate) -> str:
        header = "| Round | Claude | Gemini | ChatGPT |"
        sep = "|---|---|---|---|"
        lines = [header, sep]
        for r in debate.rounds:
            cells = {"claude": "—", "gemini": "—", "chatgpt": "—"}
            for t in r.turns:
                a = t.answer.agreed
                cells[t.elder] = "yes" if a is True else "no" if a is False else "—"
            lines.append(
                f"| R{r.number} | {cells['claude']} | {cells['gemini']} | {cells['chatgpt']} |"
            )
        return "\n".join(lines)
