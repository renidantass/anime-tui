import pytest

from app.application.title_utils import (
    audio_variant_label,
    detect_audio_variant,
    extract_episode_number,
    get_episode_number,
    is_only_episode_label,
    is_unknown_episode_number,
    normalize_watch_titles,
    prefer_display_title,
    strip_episode_suffix,
    strip_title_variants,
    title_has_variant_noise,
)


class TestExtractEpisodeNumber:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Episódio 12", "12"),
            ("Episode 5", "5"),
            ("Ep. 42", "42"),
            ("Capítulo 7", "7"),
            ("Cap. 10", "10"),
            ("S01E03", "3"),
            ("Episodio 001", "1"),
            ("E 99", "99"),
            ("# 15", "15"),
            ("Boku no Hero - 73", "73"),
            ("12", "12"),
            ("", "?"),
        ],
    )
    def test_extract_from_text(self, text, expected):
        assert extract_episode_number(text) == expected

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://example.com/episodio/12", "12"),
            ("https://example.com/episode/05", "5"),
            ("https://example.com/anime/e16/", "16"),
            ("https://example.com/anime/ep-99", "99"),
            ("https://example.com/anime_s01_ep03", "3"),
        ],
    )
    def test_extract_from_url(self, url, expected):
        assert extract_episode_number(url) == expected

    def test_fallback_order(self):
        assert extract_episode_number("", "Episode 7") == "7"

    def test_get_defaults(self):
        assert extract_episode_number("nada", default="0") == "0"

    def test_ignores_years(self):
        assert extract_episode_number("2023") == "?"

    def test_get_episode_number_alias(self):
        assert get_episode_number("Ep 25") == "25"


class TestStripEpisodeSuffix:
    def test_strips_episode_label(self):
        assert strip_episode_suffix("Boku no Hero - Episódio 12") == "Boku no Hero"

    def test_strips_ep_number(self):
        result = strip_episode_suffix("Attack on Titan - 05")
        assert result == "Attack on Titan"

    def test_strips_final(self):
        result = strip_episode_suffix("Solo Leveling - Episódio 12 Final")
        assert "Episódio" not in result

    def test_no_suffix(self):
        assert strip_episode_suffix("Fullmetal Alchemist") == "Fullmetal Alchemist"

    def test_empty(self):
        assert strip_episode_suffix("") == ""


class TestStripTitleVariants:
    def test_strips_dublado(self):
        assert "Dublado" not in strip_title_variants("Naruto Dublado")

    def test_strips_legendado(self):
        assert "Legendado" not in strip_title_variants("One Piece Legendado")

    def test_strips_hd(self):
        assert "HD" not in strip_title_variants("Demon Slayer 1080p")

    def test_strips_dub_tag(self):
        result = strip_title_variants("Hunter x Hunter (Dub)")
        assert "Dub" not in result

    def test_strips_leg_tag(self):
        result = strip_title_variants("Jujutsu Kaisen [Legendado]")
        assert "Legendado" not in result

    def test_preserves_core_title(self):
        result = strip_title_variants("Bleach Dublado 720p")
        assert "Bleach" in result


class TestTitleHasVariantNoise:
    def test_detects_dublado(self):
        assert title_has_variant_noise("Naruto Dublado") is True

    def test_detects_legendado(self):
        assert title_has_variant_noise("One Piece Legendado") is True

    def test_detects_hd(self):
        assert title_has_variant_noise("Anime 1080p") is True

    def test_no_noise(self):
        assert title_has_variant_noise("Steins Gate") is False


class TestPreferDisplayTitle:
    def test_prefers_clean_title(self):
        result = prefer_display_title("Naruto Dublado HD", "Naruto")
        assert result == "Naruto"

    def test_keeps_current_if_both_noisy(self):
        result = prefer_display_title("One Piece Dublado", "One Piece Legendado")
        assert result == "One Piece Dublado"

    def test_fallback_to_candidate(self):
        result = prefer_display_title("", "Fullmetal Alchemist")
        assert result == "Fullmetal Alchemist"


class TestDetectAudioVariant:
    def test_dublado_in_title(self):
        assert detect_audio_variant(title="Naruto Dublado") == "dublado"

    def test_legendado_in_link(self):
        assert detect_audio_variant(link="/anime/one-piece-legendado") == "legendado"

    def test_dub_tag(self):
        assert detect_audio_variant(title="Hunter x Hunter (Dub)") == "dublado"

    def test_leg_url(self):
        assert detect_audio_variant(link="/leg/bleach-ep-1") == "legendado"

    def test_defaults_to_original(self):
        assert detect_audio_variant(title="Steins Gate") == "original"

    def test_empty(self):
        assert detect_audio_variant() == "original"


class TestAudioVariantLabel:
    def test_dublado(self):
        assert audio_variant_label("dublado") == "Dublado"

    def test_legendado(self):
        assert audio_variant_label("legendado") == "Legendado"

    def test_defaults_to_legendado(self):
        assert audio_variant_label("whatever") == "Legendado"


class TestIsUnknownEpisodeNumber:
    def test_unknown_values(self):
        assert is_unknown_episode_number("?") is True
        assert is_unknown_episode_number("0") is True
        assert is_unknown_episode_number("00") is True
        assert is_unknown_episode_number("000") is True
        assert is_unknown_episode_number("") is True
        assert is_unknown_episode_number(None) is True

    def test_known_values(self):
        assert is_unknown_episode_number("1") is False
        assert is_unknown_episode_number("12") is False
        assert is_unknown_episode_number("100") is False


class TestIsOnlyEpisodeLabel:
    def test_only_ep_label(self):
        assert is_only_episode_label("Episódio 5") is True
        assert is_only_episode_label("Episode 12") is True
        assert is_only_episode_label("Capítulo 3") is True

    def test_not_only_ep_label(self):
        assert is_only_episode_label("Naruto Episódio 5") is False
        assert is_only_episode_label("") is False


class TestNormalizeWatchTitles:
    def test_full_title_and_ep(self):
        anime, ep, num = normalize_watch_titles("Naruto", "Episódio 5", "5")
        assert anime == "Naruto"
        assert num == "5"

    def test_ep_in_anime_title(self):
        anime, ep, num = normalize_watch_titles("Naruto - Episódio 5", "Naruto", "5")
        assert anime == "Naruto"

    def test_no_episode(self):
        anime, ep, num = normalize_watch_titles("One Piece", "", "")
        assert anime == "One Piece"

    def test_empty_fallback(self):
        anime, _, _ = normalize_watch_titles("", "", "")
        assert anime == "Anime"
