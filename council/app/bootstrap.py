from __future__ import annotations

from council.adapters.elders.claude_code import ClaudeCodeAdapter
from council.adapters.elders.codex_cli import CodexCLIAdapter
from council.adapters.elders.gemini_cli import GeminiCLIAdapter
from council.adapters.elders.openrouter import OpenRouterAdapter
from council.app.config import AppConfig
from council.domain.models import ElderId
from council.domain.ports import ElderPort
from council.domain.roster import RosterSpec

# Default roster ships three distinct providers (Anthropic, Meta,
# OpenAI) so the adaptive policy picks full_debate mode instead of the
# low-diversity warning path on a fresh install. The slot labels
# (ada/kai/mei) are positional only; the debate protocol is slot-keyed,
# not model-keyed.
#
# Two separate evidence claims, worth distinguishing:
#   1. Don't ship homogeneous. Under every judge tested in the 2026-04-20
#      judge-swap replication (`docs/experiments/2026-04-20-judge-
#      replication.md`) a homogeneous roster landed last on synthesis
#      preference. A non-homogeneous default is evidence-backed.
#   2. The specific "substituted > mixed" ordering that the 2026-04-19
#      probe (`docs/experiments/2026-04-19-9288-homogenisation.md`)
#      initially reported was judge-family-specific and did not survive
#      judge swap. This mapping is therefore ONE reasonable non-homogeneous
#      default — not a claim that this specific trio is best-performing.
_DEFAULT_OPENROUTER_MODELS: dict[ElderId, str] = {
    "ada": "anthropic/claude-sonnet-4.5",
    "kai": "meta-llama/llama-3.1-70b-instruct",
    "mei": "openai/gpt-5",
}


def build_elders(
    config: AppConfig,
    *,
    cli_models: dict[ElderId, str | None],
) -> tuple[dict[ElderId, ElderPort], bool, RosterSpec]:
    if config.openrouter_api_key:
        elders: dict[ElderId, ElderPort] = {}
        resolved_models: dict[ElderId, str] = {}
        for eid in ("ada", "kai", "mei"):
            model = (
                cli_models.get(eid)
                or config.openrouter_models.get(eid)
                or _DEFAULT_OPENROUTER_MODELS[eid]
            )
            elders[eid] = OpenRouterAdapter(
                elder_id=eid,
                model=model,
                api_key=config.openrouter_api_key,
            )
            resolved_models[eid] = model
        return elders, True, RosterSpec(name="openrouter", models=resolved_models)

    elders = {
        "ada": ClaudeCodeAdapter(model=cli_models.get("ada")),
        "kai": GeminiCLIAdapter(model=cli_models.get("kai")),
        "mei": CodexCLIAdapter(model=cli_models.get("mei")),
    }
    return elders, False, RosterSpec(name="subprocess", models={})
