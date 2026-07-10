import json
import os
import tempfile

import pytest

from app.application.watch_history_service import WatchHistoryService


class TestWatchHistoryService:
    @pytest.fixture
    def tmp_history_file(self):
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w", encoding="utf-8"
        ) as f:
            json.dump({"entries": []}, f)
        yield f.name
        os.unlink(f.name)

    def test_add_entry(self, tmp_history_file):
        svc = WatchHistoryService(file_path=tmp_history_file)
        entry = svc.add_entry(
            anime_title="Naruto",
            episode_title="Episódio 5",
            episode_number="5",
            episode_link="https://example.com/naruto/ep/5",
            source_name="Goyabu",
        )
        assert entry.anime_title == "Naruto"
        assert entry.episode_number == "5"
        assert entry.source_name == "Goyabu"

    def test_add_entry_dedup(self, tmp_history_file):
        svc = WatchHistoryService(file_path=tmp_history_file)
        e1 = svc.add_entry(
            anime_title="Naruto",
            episode_title="Ep 5",
            episode_number="5",
            episode_link="https://example.com/naruto/ep/5",
            source_name="Goyabu",
        )
        e2 = svc.add_entry(
            anime_title="Naruto",
            episode_title="Ep 5",
            episode_number="5",
            episode_link="https://example.com/naruto/ep/5",
            source_name="Topanimes",
        )
        assert len(svc.get_all()) == 1
        assert e1 is e2

    def test_dedup_same_anime_ep(self, tmp_history_file):
        svc = WatchHistoryService(file_path=tmp_history_file)
        svc.add_entry(
            anime_title="One Piece",
            episode_title="Episódio 1",
            episode_number="1",
            episode_link="https://a.com/ep/1",
            source_name="A",
        )
        svc.add_entry(
            anime_title="One Piece",
            episode_title="Ep 1",
            episode_number="1",
            episode_link="https://b.com/ep/1",
            source_name="B",
        )
        entries = svc.get_all()
        assert len(entries) == 1

    def test_update_progress(self, tmp_history_file):
        svc = WatchHistoryService(file_path=tmp_history_file)
        svc.add_entry(
            anime_title="Bleach",
            episode_title="Ep 1",
            episode_number="1",
            episode_link="https://example.com/bleach/1",
            source_name="Test",
        )
        svc.update_progress("https://example.com/bleach/1", 120.0, 1400.0)
        assert svc.get_progress("https://example.com/bleach/1") == 120.0

    def test_get_progress_finished(self, tmp_history_file):
        svc = WatchHistoryService(file_path=tmp_history_file)
        svc.add_entry(
            anime_title="Test",
            episode_title="Ep 1",
            episode_number="1",
            episode_link="https://example.com/ep/1",
            source_name="Test",
            progress_seconds=1400.0,
            duration_seconds=1400.0,
        )
        assert svc.get_progress("https://example.com/ep/1") == 0.0

    def test_get_progress_unknown(self, tmp_history_file):
        svc = WatchHistoryService(file_path=tmp_history_file)
        assert svc.get_progress("https://example.com/unknown") == 0.0

    def test_get_all_deduped(self, tmp_history_file):
        svc = WatchHistoryService(file_path=tmp_history_file)
        svc.add_entry(
            anime_title="Naruto",
            episode_title="Ep 1",
            episode_number="1",
            episode_link="https://a.com/naruto/1",
            source_name="A",
        )
        svc.add_entry(
            anime_title="Naruto",
            episode_title="Ep 2",
            episode_number="2",
            episode_link="https://a.com/naruto/2",
            source_name="A",
        )
        deduped = svc.get_all_deduped()
        assert len(deduped) == 1
        assert deduped[0].anime_title == "Naruto"

    def test_get_all_unique_episodes(self, tmp_history_file):
        svc = WatchHistoryService(file_path=tmp_history_file)
        svc.add_entry(
            anime_title="Naruto",
            episode_title="Ep 1",
            episode_number="1",
            episode_link="https://a.com/naruto/1",
            source_name="A",
        )
        svc.add_entry(
            anime_title="Naruto",
            episode_title="Ep 2",
            episode_number="2",
            episode_link="https://a.com/naruto/2",
            source_name="A",
        )
        unique = svc.get_all_unique_episodes()
        assert len(unique) == 2

    def test_clear_all(self, tmp_history_file):
        svc = WatchHistoryService(file_path=tmp_history_file)
        svc.add_entry(
            anime_title="Test",
            episode_title="Ep 1",
            episode_number="1",
            episode_link="https://example.com/ep/1",
            source_name="Test",
        )
        assert len(svc.get_all()) == 1
        svc.clear_all()
        assert len(svc.get_all()) == 0

    def test_normalizes_titles(self, tmp_history_file):
        svc = WatchHistoryService(file_path=tmp_history_file)
        entry = svc.add_entry(
            anime_title="Naruto Dublado - Episódio 5",
            episode_title="Naruto Dublado - Episódio 5",
            episode_number="5",
            episode_link="https://example.com/naruto/5",
            source_name="Test",
        )
        assert "Episódio" not in entry.anime_title

    def test_progress_fields_default(self, tmp_history_file):
        svc = WatchHistoryService(file_path=tmp_history_file)
        entry = svc.add_entry(
            anime_title="Test",
            episode_title="Ep 1",
            episode_number="1",
            episode_link="https://example.com/ep/1",
            source_name="Test",
        )
        assert entry.progress_seconds == 0.0
        assert entry.duration_seconds == 0.0
        assert entry.progress_ratio() == 0.0
        assert entry.is_finished() is False
