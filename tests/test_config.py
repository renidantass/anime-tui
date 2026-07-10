from app.infrastructure.config import SOURCE_URL_DEFAULTS, Config


class TestConfig:
    def test_defaults(self):
        c = Config()
        assert c.player == "auto"
        assert c.enabled_sources is None
        assert c.source_urls == {}

    def test_custom_player(self):
        c = Config(player="mpv")
        assert c.player == "mpv"

    def test_empty_player_falls_back(self):
        c = Config(player="")
        assert c.player == "auto"

    def test_enabled_sources_copy(self):
        c = Config(enabled_sources=["goyabu", "animeyabu"])
        assert c.enabled_sources == ["goyabu", "animeyabu"]

    def test_source_urls(self):
        c = Config(source_urls={"animesonlinecc": "https://custom.to"})
        assert c.source_urls["animesonlinecc"] == "https://custom.to"

    def test_get_source_url_custom(self):
        c = Config(source_urls={"goyabu": "https://custom-goyabu.io"})
        assert c.get_source_url("goyabu") == "https://custom-goyabu.io"

    def test_get_source_url_fallback(self):
        c = Config()
        assert c.get_source_url("goyabu") == "https://goyabu.io"

    def test_get_source_url_unknown(self):
        c = Config()
        assert c.get_source_url("nonexistent") == ""

    def test_source_urls_not_dict(self):
        c = Config(source_urls="invalid")  # type: ignore
        assert c.source_urls == {}

    def test_to_dict(self):
        c = Config(player="mpv", source_urls={"goyabu": "https://custom-goyabu.io"})
        d = c.to_dict()
        assert d["player"] == "mpv"
        assert d["source_urls"] == {"goyabu": "https://custom-goyabu.io"}

    def test_from_dict(self):
        c = Config.from_dict({"player": "vlc", "source_urls": {"goyabu": "https://goyabu.new"}})
        assert c.player == "vlc"
        assert c.get_source_url("goyabu") == "https://goyabu.new"


class TestSourceUrlDefaults:
    def test_all_have_urls(self):
        assert SOURCE_URL_DEFAULTS["animesonlinecc"] == "https://animesonlinecc.to"
        assert SOURCE_URL_DEFAULTS["animesonlinecloud"] == "https://animesonline.cloud"
        assert SOURCE_URL_DEFAULTS["goyabu"] == "https://goyabu.io"
        assert SOURCE_URL_DEFAULTS["topanimes"] == "https://topanimes.net"
        assert SOURCE_URL_DEFAULTS["animeyabu"] == "https://www.animeyabu.net"

    def test_all_identifiers_match_sources(self):
        expected = {
            "animesonlinecc",
            "animesonlinecloud",
            "goyabu",
            "topanimes",
            "animeyabu",
        }
        assert set(SOURCE_URL_DEFAULTS.keys()) == expected
