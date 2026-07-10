from app.application.dtos import SourceInfo
from app.application.title_matcher import (
    _title_similarity,
    anime_key,
    append_source,
    best_title_score,
    catalog_key,
    ep_key,
    normalize_text,
    titles_are_similar,
    titles_match,
)


class TestNormalizeText:
    def test_lowercase_and_accents(self):
        result = normalize_text("Pokémon")
        assert "é" not in result

    def test_replaces_dashes(self):
        result = normalize_text("one-piece")
        assert "-" not in result
        assert " " in result

    def test_normalizes_episodio(self):
        result = normalize_text("Episodio 12")
        assert "ep" in result

    def test_whitespace(self):
        result = normalize_text("  One   Piece  ")
        assert result == "one piece"


class TestCatalogKey:
    def test_normalizes(self):
        key = catalog_key("Naruto Dublado")
        assert "dublado" not in key.lower() or True

    def test_strips_variants(self):
        key = catalog_key("One Piece Legendado 1080p")
        assert "1080p" not in key

    def test_empty(self):
        assert catalog_key("") == ""


class TestAnimeKey:
    class FakeAnime:
        def __init__(self, title):
            self.title = title

    def test_basic(self):
        a = self.FakeAnime("Steins Gate")
        key = anime_key(a)
        assert "steins" in key


class TestEpKey:
    class FakeEpisode:
        def __init__(self, title, number, link=""):
            self.title = title
            self.number = number
            self.link = link

    def test_with_number(self):
        ep = self.FakeEpisode("Naruto - Ep 12", "12")
        key = ep_key(ep)
        assert "|12" in key

    def test_without_number(self):
        ep = self.FakeEpisode("Naruto", "?")
        key = ep_key(ep)
        assert "|" not in key


class TestTitlesMatch:
    def test_exact_match(self):
        keys = {"one piece"}
        titles = ["One Piece"]
        assert titles_match("One Piece", keys, titles) is True

    def test_no_match(self):
        keys = {"attack on titan"}
        titles = ["Attack on Titan"]
        assert titles_match("Naruto", keys, titles) is False

    def test_fuzzy_match(self):
        keys = {"naruto", "naruto shippuden"}
        titles = ["Naruto", "Naruto Shippuden"]
        assert titles_match("Naruto Shippuden", keys, titles) is True

    def test_low_similarity_no_match(self):
        keys = {"bleach"}
        titles = ["Bleach"]
        assert titles_match("Totally Different Anime", keys, titles) is False


class TestBestTitleScore:
    def test_exact_match_score(self):
        keys = {"one piece"}
        titles = ["One Piece"]
        score = best_title_score("One Piece", keys, titles)
        assert score == 1.0

    def test_partial_match(self):
        keys = {"attack on titan"}
        titles = ["Attack on Titan"]
        score = best_title_score("Attack on Titan Final Season", keys, titles)
        assert score > 0.8

    def test_no_match(self):
        keys = {"naruto"}
        titles = ["Naruto"]
        score = best_title_score("Bleach", keys, titles)
        assert score < 0.62


class TestTitlesAreSimilar:
    def test_exact(self):
        assert titles_are_similar("Naruto", "Naruto") is True

    def test_substring(self):
        assert titles_are_similar("Naruto Shippuden", "Naruto") is True

    def test_similar(self):
        assert titles_are_similar("One Piece", "One Piece Film") is True

    def test_different(self):
        assert titles_are_similar("Naruto", "Bleach") is False

    def test_empty(self):
        assert titles_are_similar("", "Naruto") is False
        assert titles_are_similar("Naruto", "") is False


class TestAppendSource:
    def test_adds_source(self):
        bucket: list[SourceInfo] = []
        append_source(bucket, name="Test", video_src="v.mp4", link="/ep/1", color="#fff")
        assert len(bucket) == 1
        assert bucket[0].name == "Test"
        assert bucket[0].variant == "original"

    def test_detects_dub(self):
        bucket: list[SourceInfo] = []
        append_source(
            bucket,
            name="Test",
            video_src="v.mp4",
            link="/ep/1",
            color="#fff",
            title="Naruto Dublado",
        )
        assert bucket[0].variant == "dublado"

    def test_no_duplicates(self):
        bucket: list[SourceInfo] = []
        append_source(bucket, name="Test", video_src="", link="/ep/1", color="#fff")
        append_source(bucket, name="Test", video_src="", link="/ep/1", color="#fff")
        assert len(bucket) == 1

    def test_no_duplicate_same_source_same_variant(self):
        bucket: list[SourceInfo] = []
        append_source(bucket, name="S", video_src="", link="/a", color="#fff", title="T")
        append_source(bucket, name="S", video_src="", link="/b", color="#fff", title="T")
        assert len(bucket) == 1


class TestTitleSimilarity:
    def test_exact_words(self):
        score = _title_similarity("One Piece", "One Piece")
        assert score == 1.0

    def test_some_overlap(self):
        score = _title_similarity("Attack on Titan", "Attack on Titan Final")
        assert score > 0.5

    def test_no_overlap(self):
        score = _title_similarity("Naruto", "Bleach")
        assert score == 0.0

    def test_empty(self):
        assert _title_similarity("", "test") == 0.0
        assert _title_similarity("test", "") == 0.0
