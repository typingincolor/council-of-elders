"""Debate report generation.

Produces a markdown "debate report" for a completed debate: a deterministic
metadata header (rounds, questions, convergence timeline) plus an
LLM-generated narrative (positions, pivots, concessions).

This module is pure — no I/O, no LLM calls. It builds the text inputs
that DebateService consumes (and the prompt it sends to the elder).
"""

from __future__ import annotations

import re

from council.domain.models import Debate, ElderAnswer, ElderId

_PROMPT_HEADER_LIMIT = 200


def _truncate_prompt(prompt: str, limit: int = _PROMPT_HEADER_LIMIT) -> tuple[str, bool]:
    """Return (short_form, was_truncated).

    Prefers the first sentence; falls back to the first `limit` chars with
    an ellipsis. Used to keep the report header readable when the user has
    pasted a lot of source material into the original prompt.
    """
    stripped = prompt.strip()
    first_line = stripped.split("\n", 1)[0].strip()
    if first_line == stripped and len(first_line) <= limit:
        return stripped, False
    m = re.search(r"[.!?](?:\s|$)", first_line)
    if m and m.end() <= limit:
        short = first_line[: m.end()].strip()
    elif len(first_line) <= limit:
        short = first_line
    else:
        short = first_line[:limit].rstrip() + "…"
    return short, True


def _demote_markdown_headings(text: str, levels: int = 2) -> str:
    """Shift ATX-style markdown headings deeper by `levels`, clamped at 6.

    Preserves code fences (lines inside ``` blocks are never rewritten).
    Used when embedding elder-produced or synthesiser-produced markdown
    inside a report whose own heading structure uses ##/### — without
    demotion, a model's `## Response` inside an answer would collide with
    the report's own outline.
    """
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        m = re.match(r"^(#{1,6})(\s+.*)$", line)
        if m:
            new_level = min(len(m.group(1)) + levels, 6)
            out.append("#" * new_level + m.group(2))
        else:
            out.append(line)
    return "\n".join(out)


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
        one more job after synthesis: describe what happened, with an
        explicit check on whether "CONVERGED: yes" was real consensus or
        merely procedural agreement to stop.
        """
        return (
            "You have just synthesised a council-of-elders debate. Now write a "
            "brief analysis (~200-300 words, markdown) of HOW the debate "
            "unfolded and whether the elders really agreed. Cover:\n\n"
            "- Each elder's opening position in round 1, in one sentence each.\n"
            "- The key tensions or disagreements that surfaced in round 2 and beyond.\n"
            "- Any notable concessions or shifts in position across rounds.\n"
            "- How convergence evolved — who converged first, what probes remained.\n\n"
            "**CRITICAL — consensus check. This is the most important part.** "
            "The elders may all have said `CONVERGED: yes` but still produced "
            "materially different final answers — a false consensus driven by "
            "agreement on *philosophy* while disagreeing on *wording*. You MUST:\n\n"
            "- Compare the elders' FINAL-round answers word-for-word.\n"
            "- Flag any substantive differences — wording choices that change "
            "meaning, not stylistic preferences.\n"
            "- State explicitly: was this *real consensus on the answer*, or "
            "only *procedural agreement to stop debating*?\n"
            "- If there is real unresolved divergence, name it plainly and say "
            "what the user should decide for themselves.\n\n"
            'Write in past tense, third-person (e.g. "Claude argued…", "Gemini '
            'conceded…"). Do NOT repeat the synthesised answer; summarise the '
            "process and audit the consensus. Start directly with the content "
            "— no preamble, no heading."
        )

    def build_final_positions_section(self, debate: Debate) -> str:
        """Side-by-side of each elder's final-round answer text.

        Surfaces false-consensus: even when all three said CONVERGED: yes,
        their final answers may differ in meaning-changing ways. The
        reader can eyeball the differences directly.

        Elder-emitted markdown headings are demoted by two levels so a
        model's own `## Foo` inside the answer doesn't collide with the
        report's outline (where each elder gets a `###` heading).
        """
        if not debate.rounds:
            return ""
        last = debate.rounds[-1]
        lines = ["## Final positions (each elder's last-round answer)", ""]
        for t in last.turns:
            agreed = t.answer.agreed
            label = (
                "CONVERGED: yes"
                if agreed is True
                else "CONVERGED: no"
                if agreed is False
                else "(no convergence tag)"
            )
            lines.append(f"### {_ELDER_LABEL[t.elder]} — _{label}_")
            lines.append("")
            body = t.answer.text or "_(no text)_"
            lines.append(_demote_markdown_headings(body))
            lines.append("")
        return "\n".join(lines).rstrip()

    def assemble_report_markdown(
        self,
        debate: Debate,
        synthesis: ElderAnswer,
        narrative: str,
        *,
        synthesiser: ElderId,
    ) -> str:
        """Combine everything into the final markdown file content."""
        short_prompt, prompt_truncated = _truncate_prompt(debate.prompt)

        parts: list[str] = []
        parts.append(f"# Council of Elders — debate `{debate.id}`")
        parts.append("")
        parts.append(f"**Question:** {short_prompt}")
        if prompt_truncated:
            parts.append("")
            parts.append("_(full source material appears at the end of this report)_")
        parts.append("")
        parts.append(f"**Synthesised by:** {_ELDER_LABEL[synthesiser]}")
        parts.append("")
        parts.append("## Synthesised answer")
        parts.append("")
        synth_text = synthesis.text or "_(no text)_"
        parts.append(_demote_markdown_headings(synth_text))
        parts.append("")
        parts.append(self.build_metadata_section(debate))
        parts.append("")
        final_positions = self.build_final_positions_section(debate)
        if final_positions:
            parts.append(final_positions)
            parts.append("")
        parts.append("## Narrative & consensus audit")
        parts.append("")
        parts.append(_demote_markdown_headings(narrative.strip()))
        parts.append("")
        if prompt_truncated:
            parts.append("## Full question (source material)")
            parts.append("")
            parts.append(debate.prompt.strip())
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
