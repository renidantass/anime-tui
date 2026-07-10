from app.application.dtos import (
    AnimeDetail,
    AnimeEntry,
    EpisodeEntry,
    EpisodeItem,
    PlayCandidate,
    PlayResult,
    ResolvedPlay,
    SeasonDetail,
    SourceEntry,
    SourceInfo,
)


class TestSourceEntry:
    def test_defaults(self):
        entry = SourceEntry(name="Test", identifier="test", color="#fff")
        assert entry.name == "Test"
        assert entry.identifier == "test"
        assert entry.color == "#fff"
        assert entry.has_search is True
        assert entry.has_details is True
        assert entry.available is True
        assert entry.error == ""
        assert entry.base_url == ""
        assert entry.status == "unknown"
        assert entry.latency_ms is None
        assert entry.checks_total == 0
        assert entry.checks_ok == 0
        assert entry.uptime_percent is None
        assert entry._recent == []

    def test_custom_values(self):
        entry = SourceEntry(
            name="Goyabu",
            identifier="goyabu",
            color="#3498db",
            has_search=True,
            has_details=True,
            base_url="https://goyabu.io",
        )
        assert entry.base_url == "https://goyabu.io"
        assert entry.has_search is True

    def test_recent_list_is_independent(self):
        e1 = SourceEntry(name="A", identifier="a", color="#000")
        e2 = SourceEntry(name="B", identifier="b", color="#fff")
        e1._recent.append(True)
        assert e2._recent == []

    def test_mutable_fields(self):
        entry = SourceEntry(name="X", identifier="x", color="#000")
        entry.status = "online"
        entry.latency_ms = 42.5
        entry.available = False
        assert entry.status == "online"
        assert entry.latency_ms == 42.5
        assert entry.available is False


class TestSourceInfo:
    def test_basic(self):
        s = SourceInfo(name="Test", video_src="https://example.com/v.mp4", link="/ep/1")
        assert s.name == "Test"
        assert s.video_src == "https://example.com/v.mp4"
        assert s.link == "/ep/1"

    def test_defaults(self):
        s = SourceInfo(name="X", video_src="", link="")
        assert s.color == ""
        assert s.variant == ""
        assert s.title == ""


class TestEpisodeEntry:
    def test_basic(self):
        e = EpisodeEntry(title="Naruto Ep 1", image="img.jpg", date="2024-01-01")
        assert e.title == "Naruto Ep 1"
        assert e.sources == []
        assert e.number == ""

    def test_with_sources(self):
        s = SourceInfo(name="Goyabu", video_src="v.mp4", link="/ep/1")
        e = EpisodeEntry(title="Test", image="", date="", sources=[s], number="1")
        assert len(e.sources) == 1
        assert e.sources[0].name == "Goyabu"
        assert e.number == "1"

    def test_default_sources_are_empty(self):
        e = EpisodeEntry(title="T", image="", date="")
        assert e.sources == []
        e.sources.append(SourceInfo(name="X", video_src="", link=""))
        assert len(e.sources) == 1


class TestAnimeEntry:
    def test_basic(self):
        a = AnimeEntry(title="Naruto", rating="8.5", image="poster.jpg")
        assert a.title == "Naruto"
        assert a.rating == "8.5"
        assert a.sources == []
        assert a.anilist_id is None
        assert a.meta == {}

    def test_with_meta_and_anilist(self):
        a = AnimeEntry(
            title="Steins Gate",
            rating="9.0",
            image="img.jpg",
            anilist_id=9253,
            meta={"year": 2011, "studios": ["White Fox"]},
        )
        assert a.anilist_id == 9253
        assert a.meta["year"] == 2011

    def test_default_meta_independent(self):
        a1 = AnimeEntry(title="A", rating="", image="")
        a2 = AnimeEntry(title="B", rating="", image="")
        a1.meta["key"] = "val"
        assert a2.meta == {}


class TestDataclassDTOs:
    def test_episode_item(self):
        item = EpisodeItem(number="1", title="Ep 1", link="/ep/1", video_src="v.mp4")
        assert item.number == "1"
        assert item.image == ""

    def test_season_detail(self):
        ep = EpisodeItem(number="1", title="Ep 1", link="/ep/1", video_src="")
        season = SeasonDetail(number=1, episodes=[ep])
        assert season.number == 1
        assert len(season.episodes) == 1

    def test_anime_detail(self):
        ep = EpisodeItem(number="1", title="Ep 1", link="/ep/1", video_src="")
        season = SeasonDetail(number=1, episodes=[ep])
        detail = AnimeDetail(
            title="Naruto",
            rating="8.0",
            link="/naruto",
            description="A ninja story",
            seasons=[season],
        )
        assert detail.description == "A ninja story"
        assert len(detail.seasons) == 1

    def test_play_candidate(self):
        c = PlayCandidate(name="SourceA", link="/ep/1", color="#f00")
        assert c.name == "SourceA"

    def test_resolved_play_defaults(self):
        rp = ResolvedPlay(playable=True)
        assert rp.tried == []

    def test_play_result_defaults(self):
        pr = PlayResult(
            playable=True,
            stream_url="https://example.com/stream.mp4",
            page_url="https://example.com/page",
            external_url=None,
            is_hls=False,
            start_at=0.0,
            token=None,
            source_name="Test",
            source_color="#fff",
            episode_link="/ep/1",
            switched=False,
        )
        assert pr.tried == []
