"""Offline tests for PlayDead's non-network logic.

These exercise the parts that don't require archive.org or an audio player:
date parsing, best-tape ranking, playlist building, nickname resolution, and
playback state persistence.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / ".claude" / "skills" / "playdead" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import archive  # noqa: E402
import famous_shows  # noqa: E402


class TestDateParsing(unittest.TestCase):
    def test_iso(self):
        self.assertEqual(archive.parse_date("1977-05-08"), "1977-05-08")

    def test_iso_in_sentence(self):
        self.assertEqual(archive.parse_date("play 1972-08-27 please"), "1972-08-27")

    def test_slash_four_digit_year(self):
        self.assertEqual(archive.parse_date("5/8/1977"), "1977-05-08")

    def test_slash_two_digit_year(self):
        self.assertEqual(archive.parse_date("5/8/77"), "1977-05-08")

    def test_dash_two_digit_year(self):
        self.assertEqual(archive.parse_date("8-27-72"), "1972-08-27")

    def test_invalid_month(self):
        self.assertIsNone(archive.parse_date("13/40/77"))

    def test_no_date(self):
        self.assertIsNone(archive.parse_date("the cornell show"))


class TestSourceClassification(unittest.TestCase):
    def test_soundboard_from_identifier(self):
        show = {"identifier": "gd1977-05-08.sbd.hicks.4982.sbeok.shnf", "title": "", "source": ""}
        self.assertEqual(archive.classify_source(show), "SBD")

    def test_matrix(self):
        show = {"identifier": "gd1977-05-08.matrix.seamons", "title": "", "source": ""}
        self.assertEqual(archive.classify_source(show), "MATRIX")

    def test_audience(self):
        show = {"identifier": "gd1977-05-08.aud.vernon", "title": "", "source": "AUD"}
        self.assertEqual(archive.classify_source(show), "AUD")

    def test_unknown(self):
        show = {"identifier": "gd1977-05-08.12345", "title": "Grateful Dead", "source": ""}
        self.assertEqual(archive.classify_source(show), "UNKNOWN")


class TestRanking(unittest.TestCase):
    def test_soundboard_beats_audience(self):
        sbd = {"identifier": "gd.sbd", "title": "", "source": "", "avg_rating": 4.0,
               "num_reviews": 10, "downloads": 1000}
        aud = {"identifier": "gd.aud", "title": "", "source": "", "avg_rating": 5.0,
               "num_reviews": 50, "downloads": 5000}
        sbd["source_type"] = archive.classify_source(sbd)
        aud["source_type"] = archive.classify_source(aud)
        self.assertGreater(archive.score_show(sbd), archive.score_show(aud))

    def test_ratings_break_ties(self):
        a = {"identifier": "gd.sbd.a", "title": "", "source": "", "avg_rating": 4.8,
             "num_reviews": 20, "downloads": 2000}
        b = {"identifier": "gd.sbd.b", "title": "", "source": "", "avg_rating": 3.0,
             "num_reviews": 20, "downloads": 2000}
        for s in (a, b):
            s["source_type"] = archive.classify_source(s)
        self.assertGreater(archive.score_show(a), archive.score_show(b))


class TestPlaylist(unittest.TestCase):
    METADATA = {
        "metadata": {"identifier": "gd1977-05-08.sbd.hicks.4982.sbeok.shnf",
                     "title": "Grateful Dead Live at Barton Hall"},
        "files": [
            {"name": "gd77-05-08d1t02.mp3", "title": "New Minglewood Blues",
             "track": "2", "format": "VBR MP3", "length": "300"},
            {"name": "gd77-05-08d1t01.mp3", "title": "The Music Never Stopped",
             "track": "1", "format": "VBR MP3", "length": "400"},
            {"name": "gd77-05-08.txt", "format": "Text"},
            {"name": "gd77-05-08d1t01.flac", "track": "1", "format": "Flac"},
        ],
    }

    def test_orders_by_track_and_prefers_mp3(self):
        pl = archive.build_playlist(self.METADATA)
        self.assertEqual(len(pl), 2)  # only the two mp3s
        self.assertEqual(pl[0]["title"], "The Music Never Stopped")
        self.assertEqual(pl[1]["title"], "New Minglewood Blues")

    def test_builds_download_urls(self):
        pl = archive.build_playlist(self.METADATA)
        self.assertTrue(pl[0]["url"].startswith(
            "https://archive.org/download/gd1977-05-08.sbd.hicks.4982.sbeok.shnf/"))
        self.assertTrue(pl[0]["url"].endswith("gd77-05-08d1t01.mp3"))

    def test_falls_back_to_ogg_when_no_mp3(self):
        md = {"metadata": {"identifier": "x"},
              "files": [{"name": "t1.ogg", "track": "1"}, {"name": "info.txt"}]}
        pl = archive.build_playlist(md)
        self.assertEqual(len(pl), 1)
        self.assertTrue(pl[0]["url"].endswith("t1.ogg"))

    def test_no_audio_returns_empty(self):
        md = {"metadata": {"identifier": "x"}, "files": [{"name": "notes.txt"}]}
        self.assertEqual(archive.build_playlist(md), [])


class TestIdentifier(unittest.TestCase):
    def test_recognises_identifier(self):
        self.assertTrue(archive.is_identifier("gd1977-05-08.sbd.hicks.4982"))

    def test_rejects_plain_text(self):
        self.assertFalse(archive.is_identifier("cornell"))
        self.assertFalse(archive.is_identifier("1977-05-08"))


class TestFamousShows(unittest.TestCase):
    def test_cornell(self):
        self.assertEqual(famous_shows.resolve_alias("cornell")[0], "1977-05-08")

    def test_substring(self):
        self.assertEqual(
            famous_shows.resolve_alias("play the veneta show")[0], "1972-08-27")

    def test_unknown(self):
        self.assertIsNone(famous_shows.resolve_alias("some random gig"))


class TestState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["PLAYDEAD_HOME"] = self.tmp
        # import after env is set so paths resolve under the temp dir
        import importlib
        global state
        import state  # noqa: F811
        importlib.reload(state)

    def tearDown(self):
        os.environ.pop("PLAYDEAD_HOME", None)

    def test_save_load_clear(self):
        state.save({"identifier": "gd1977-05-08", "index": 3})
        self.assertEqual(state.load()["index"], 3)
        state.clear()
        self.assertEqual(state.load(), {})

    def test_is_running_false_for_dead_pid(self):
        state.save({"pid": 2 ** 30, "backend": "mpv"})  # implausible pid
        self.assertIsNone(state.is_running())


if __name__ == "__main__":
    unittest.main(verbosity=2)
