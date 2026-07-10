from app.infrastructure.http_cache import clear, get_cached, set_cached


class TestHttpCache:
    def setup_method(self):
        clear()

    def test_set_and_get(self):
        set_cached("GET", "https://example.com/data", "hello world")
        assert get_cached("GET", "https://example.com/data") == "hello world"

    def test_miss(self):
        assert get_cached("GET", "https://unknown.com/path") is None

    def test_different_method(self):
        set_cached("POST", "https://example.com/data", "result")
        assert get_cached("GET", "https://example.com/data") is None

    def test_different_url(self):
        set_cached("GET", "https://example.com/a", "data")
        assert get_cached("GET", "https://example.com/b") is None

    def test_overwrite(self):
        set_cached("GET", "https://example.com/data", "old")
        set_cached("GET", "https://example.com/data", "new")
        assert get_cached("GET", "https://example.com/data") == "new"

    def test_clear(self):
        set_cached("GET", "https://example.com/data", "value")
        assert get_cached("GET", "https://example.com/data") == "value"
        clear()
        assert get_cached("GET", "https://example.com/data") is None
