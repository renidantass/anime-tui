from app.application.security import is_blogger_url, is_safe_url


class TestIsSafeUrl:
    def test_valid_https(self):
        assert is_safe_url("https://animesonlinecc.to/episodio/") is True

    def test_valid_http(self):
        assert is_safe_url("http://example.com/video.mp4") is True

    def test_invalid_scheme(self):
        assert is_safe_url("ftp://example.com/file") is False
        assert is_safe_url("file:///etc/passwd") is False
        assert is_safe_url("javascript:alert(1)") is False

    def test_localhost_blocked(self):
        assert is_safe_url("http://localhost:8080/test") is False
        assert is_safe_url("https://localhost/test") is False
        assert is_safe_url("http://app.localhost:3000") is False

    def test_private_ip_blocked(self):
        assert is_safe_url("http://127.0.0.1/test") is False
        assert is_safe_url("http://192.168.1.1/test") is False
        assert is_safe_url("http://10.0.0.1/test") is False
        assert is_safe_url("http://172.16.0.1/test") is False

    def test_loopback_blocked(self):
        assert is_safe_url("http://[::1]/test") is False
        assert is_safe_url("http://0.0.0.0/test") is False

    def test_link_local_blocked(self):
        assert is_safe_url("http://169.254.1.1/test") is False

    def test_local_domains_blocked(self):
        assert is_safe_url("http://app.local/test") is False
        assert is_safe_url("http://app.internal/test") is False
        assert is_safe_url("http://app.intranet/test") is False
        assert is_safe_url("http://app.lan/test") is False

    def test_empty_and_none(self):
        assert is_safe_url("") is False
        assert is_safe_url(None) is False

    def test_too_long(self):
        long_url = "https://example.com/" + "a" * 4096
        assert is_safe_url(long_url) is False

    def test_control_characters(self):
        assert is_safe_url("https://example.com/\x00test") is False

    def test_userinfo_blocked(self):
        assert is_safe_url("http://user:pass@example.com/test") is False

    def test_no_hostname(self):
        assert is_safe_url("https:///path") is False


class TestIsBloggerUrl:
    def test_blogger_token_url(self):
        assert is_blogger_url("https://www.blogger.com/video.g?token=abc123def456") is True

    def test_non_blogger_url(self):
        assert is_blogger_url("https://youtube.com/watch?v=abc") is False

    def test_empty(self):
        assert is_blogger_url("") is False
        assert is_blogger_url(None) is False
