from council.adapters.elders.gemini_cli import _sanitize


class TestGeminiSanitizer:
    def test_strips_mcp_chrome_line_when_on_its_own_line(self):
        raw = "MCP issues detected. Run /mcp list for status.\nReal answer here."
        assert _sanitize(raw) == "Real answer here."

    def test_strips_mcp_chrome_when_concatenated_with_reply(self):
        raw = "MCP issues detected. Run /mcp list for status.Right, this is my answer."
        assert _sanitize(raw) == "Right, this is my answer."

    def test_strips_cached_credentials_notice(self):
        raw = "Loaded cached credentials.\nAnswer."
        assert _sanitize(raw) == "Answer."

    def test_strips_multiple_noise_prefixes_in_order(self):
        raw = (
            "Loaded cached credentials.\n"
            "MCP issues detected. Run /mcp list for status.\n"
            "Actual content."
        )
        assert _sanitize(raw) == "Actual content."

    def test_leaves_content_unchanged_when_no_noise(self):
        raw = "Here is a clean reply with no chrome."
        assert _sanitize(raw) == raw

    def test_preserves_content_that_merely_mentions_mcp(self):
        raw = "The MCP protocol is interesting. Here is my take."
        # The noise-strip matches from the start only; generic mentions stay.
        assert _sanitize(raw) == raw

    def test_empty_input(self):
        assert _sanitize("") == ""
