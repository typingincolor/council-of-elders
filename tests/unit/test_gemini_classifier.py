from council.adapters.elders.gemini_cli import _classify


class TestGeminiClassifier:
    def test_quota_exhausted_from_quota_keyword(self):
        assert _classify("Error: quota exceeded for model gemini-pro") == "quota_exhausted"

    def test_quota_exhausted_from_rate_limit(self):
        assert _classify("429: rate limit exceeded") == "quota_exhausted"

    def test_quota_exhausted_from_resource_exhausted(self):
        assert _classify("RESOURCE_EXHAUSTED: daily limit reached") == "quota_exhausted"

    def test_quota_exhausted_from_too_many_requests(self):
        assert _classify("HTTP 429 Too Many Requests") == "quota_exhausted"

    def test_auth_failed_from_credential_error(self):
        assert _classify("No valid credential found") == "auth_failed"

    def test_auth_failed_from_unauthenticated(self):
        assert _classify("UNAUTHENTICATED: caller is not authenticated") == "auth_failed"

    def test_quota_wins_over_auth_when_both_substrings_present(self):
        # "login quota" — quota check runs first, so it should win
        assert _classify("please login and check your quota") == "quota_exhausted"

    def test_nonzero_exit_fallback(self):
        assert _classify("Segmentation fault") == "nonzero_exit"

    def test_empty_stderr_is_nonzero_exit(self):
        assert _classify("") == "nonzero_exit"
