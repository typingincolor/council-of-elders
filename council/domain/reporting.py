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
from council.domain.synthesis_output import parse_synthesis

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
    "ada": "Ada",
    "kai": "Kai",
    "mei": "Mei",
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

        Rewrite origin: produced by running the council on the previous
        version of this prompt (debate 8b60d9dc). The rewrite replaces
        mechanical instructions like "word-for-word" with an operational
        substitution test, bans ATX headings at every level (not just
        leading), adds an explicit hedge for genuinely harmonious debates
        to avoid manufactured tension, softens the quotation requirement
        to reduce fabrication risk on weaker-retrieval models, and forces
        a binary concluding sentence.
        """
        return (
            "You have just synthesised a council-of-elders debate. Now write a "
            "process-and-audit note for a technical user who will decide "
            "whether to trust the synthesised answer or investigate "
            "divergences.\n\n"
            "Length: aim for 250-400 words on harmonious debates; go longer "
            "when real divergence requires quoted spans and attribution to be "
            "explicit. Do NOT pad a harmonious narrative to hit a target — "
            "content quality beats length compliance. Format: plain prose "
            "paragraphs and short bullets permitted. Do NOT use markdown "
            "headings of any level — no `#`, `##`, or `###`. Bold and inline "
            "code are fine. Start directly with the content; no preamble, no "
            "title.\n\n"
            'Voice: past tense, third person. Name elders explicitly ("Ada '
            'argued…", "Kai conceded…"). If you are one of the elders, '
            "refer to your past turns in the third person by your own name.\n\n"
            "Cover, in roughly this order:\n\n"
            "1. Each elder's round-1 opening stance in one sentence.\n"
            "2. The real points of friction from round 2 onward — disagreements "
            "that moved the debate, not every minor quibble. If the debate was "
            "largely harmonious, say so plainly rather than inventing tension.\n"
            "3. Concessions, shifts, or holdouts. Do not assume convergence was "
            "linear; if it was partial or non-monotonic, describe that. "
            "Productive disagreement is a valid terminal state — do not frame "
            "non-convergence as a failure or defect; frame it as the council's "
            "honest verdict on an unresolved question.\n\n"
            "Then perform TWO audits in order.\n\n"
            "**Task-fidelity audit.** Compare the synthesised answer against "
            "the user's ORIGINAL question. Did the synthesis answer the "
            "question the user asked, in the SHAPE the user asked for? If "
            "the user asked for a headline, did they get a headline — or a "
            "multi-clause mission statement technically compliant but "
            "violating the spirit? If the user asked for a concrete plan, "
            "did they get one — or an abstract framing? If the debate drifted "
            "into an adjacent but different question, name the drift plainly "
            "and say what the user actually asked for. If the synthesis is a "
            "faithful answer to the original question, say so briefly.\n\n"
            "**Consensus audit.** The elders may have all declared "
            "`CONVERGED: yes` while their final-round answers still differ "
            "in ways that matter. Apply this test:\n\n"
            "> Treat wording as stylistic only if substituting one elder's "
            "wording for another would not change what a careful technical "
            "user would do. If any difference would change action, "
            "interpretation, scope, caveats, confidence, or edge-case "
            "handling, it is a material divergence.\n\n"
            "For any material divergence, name the specific differing claim "
            "and, where you can do so faithfully from the transcript, include "
            "a short quoted span with attribution. Do not paraphrase the "
            "difference away and do not restate the synthesised answer.\n\n"
            "Conclude with one explicit sentence whose leading verdict is "
            'either "This was real consensus on the answer" OR "This was '
            'procedural agreement with unresolved divergence on X," where X '
            "is named concretely. Keep that leading verdict phrase intact — "
            "do not invent a middle category. If the answer is real consensus "
            "but a small residual point is worth flagging, you may extend the "
            'sentence (e.g. "This was real consensus on the answer, with a '
            'minor residual point on Y"), so long as the leading verdict '
            'stays "real consensus" and Y is genuinely small. In the '
            "procedural-agreement case, add one sentence on what the user "
            "needs to inspect or decide."
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
        structured = parse_synthesis(synthesis.text or "")
        parts.append("## Synthesised answer")
        parts.append("")
        parts.append(_demote_markdown_headings(structured.answer or "_(no text)_"))
        parts.append("")
        if structured.why:
            parts.append("**Why:** " + structured.why)
            parts.append("")
        if structured.disagreements:
            # Primary section (before debate metadata) — surfaces dissent
            # to the reader rather than hiding it in the audit footer.
            parts.append("## Unresolved disagreements")
            parts.append("")
            for d in structured.disagreements:
                parts.append(f"- {d}")
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
        # Both terminal states are valid under the diversity-engine direction —
        # convergence is informational, not a success metric. "Productive
        # disagreement" is an equally legitimate outcome.
        for r in debate.rounds:
            if r.converged():
                return f"Reached consensus in round {r.number}."
        return f"Retained productive disagreement across all {len(debate.rounds)} rounds."

    def _convergence_table(self, debate: Debate) -> str:
        header = "| Round | Ada | Kai | Mei |"
        sep = "|---|---|---|---|"
        lines = [header, sep]
        for r in debate.rounds:
            cells = {"ada": "—", "kai": "—", "mei": "—"}
            for t in r.turns:
                a = t.answer.agreed
                cells[t.elder] = "yes" if a is True else "no" if a is False else "—"
            lines.append(
                f"| R{r.number} | {cells['ada']} | {cells['kai']} | {cells['mei']} |"
            )
        return "\n".join(lines)
