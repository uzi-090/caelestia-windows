"""Lyrics matching, timing, caching and stale-response regression checks."""
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lyrics import LyricsWorker, parse_lrc, candidate_score, query_track
from http_client import HttpStatusError


def fixture(title='Test song', artist='Sample artist', duration=180, synced=True):
    return dict(trackName=title, artistName=artist, albumName='Test album', duration=duration,
                instrumental=False, plainLyrics='First original test line\nSecond original test line',
                syncedLyrics='[00:01.00]First original test line\n[00:03.25]Second original test line' if synced else '')


class LyricsTests(unittest.TestCase):
    def test_lrc_multiple_timestamps_offset_and_fractions(self):
        lines = parse_lrc('[offset:-100]\n[00:03.1][01:04.250]Original test\n[00:01.00]Earlier test\n[ar:Metadata]')
        self.assertEqual([round(line['time'], 3) for line in lines], [0.9, 3.0, 64.15])
        self.assertEqual(lines[-1]['text'], 'Original test')

    def test_match_rejects_wrong_recording_or_artist(self):
        track = dict(title='Test song', artist='Sample artist', album='Test album', duration=180)
        self.assertGreater(candidate_score(fixture(), track), 0)
        self.assertLess(candidate_score(fixture(artist='Different performer'), track), 0)
        self.assertLess(candidate_score(fixture(duration=220), track), 0)
        self.assertLess(candidate_score(fixture(title='Test song remix'), track), 0)

    def test_collaboration_artist_subset_matches(self):
        track = dict(title='Test song', artist='Sample artist, Guest singer', album='', duration=180)
        self.assertGreater(candidate_score(fixture(), track), 0)

    def test_youtube_music_title_cleanup_preserves_versions(self):
        result = query_track(dict(title='Sample artist - Test song (Official Audio)', artist='SampleVEVO', duration=180))
        self.assertEqual((result['title'], result['artist']), ('Test song', 'Sample artist'))
        self.assertIn('remix', query_track(dict(title='Test song (remix)', artist='Sample'))['title'])

    def test_positive_cache_and_plain_fallback(self):
        calls = []
        def fetch(url):
            calls.append(url)
            return fixture(synced=False)
        with tempfile.TemporaryDirectory(prefix='caelestia-lyrics-test-') as directory:
            worker = LyricsWorker(lambda value:None, directory, fetch=fetch, autostart=False)
            track = dict(title='Test song', artist='Sample artist', album='Test album', duration=180)
            self.assertEqual(worker._load_track(track)['state'], 'plain')
            self.assertEqual(worker._load_track(track)['state'], 'plain')
            self.assertEqual(len(calls), 1)

    def test_not_found_is_a_valid_state_not_an_error(self):
        def fetch(url):
            if '/get?' in url:
                raise HttpStatusError(404)
            return []
        with tempfile.TemporaryDirectory(prefix='caelestia-lyrics-test-') as directory:
            worker = LyricsWorker(lambda value:None, directory, fetch=fetch, autostart=False)
            self.assertEqual(worker._load_track(dict(title='Unknown test', artist='Sample artist', album='', duration=180))['state'], 'not_found')

    def test_instrumental_record(self):
        record = {**fixture(), 'instrumental': True}
        with tempfile.TemporaryDirectory(prefix='caelestia-lyrics-test-') as directory:
            worker = LyricsWorker(lambda value:None, directory, fetch=lambda url:record, autostart=False)
            self.assertEqual(worker._load_track(dict(title='Test song', artist='Sample artist', album='', duration=180))['state'], 'instrumental')

    def test_late_old_response_cannot_overwrite_new_track(self):
        started, release, finished = threading.Event(), threading.Event(), threading.Event()
        results = []
        def fetch(url):
            title = parse_qs(urlsplit(url).query)['track_name'][0]
            if title == 'Old test':
                started.set()
                release.wait(2)
            return fixture(title=title)
        def publish(result):
            results.append(result)
            if result['trackKey']=='new' and result['state']=='synced':finished.set()
        with tempfile.TemporaryDirectory(prefix='caelestia-lyrics-test-') as directory:
            worker = LyricsWorker(publish, directory, fetch=fetch)
            try:
                worker.request(dict(available=True, trackId='old', title='Old test', artist='Sample artist', duration=180))
                self.assertTrue(started.wait(2))
                worker.request(dict(available=True, trackId='new', title='New test', artist='Sample artist', duration=180))
                release.set()
                self.assertTrue(finished.wait(2))
                self.assertFalse(any(item['trackKey']=='old' and item['state']=='synced' for item in results))
            finally:
                release.set()
                worker.stop()

    def test_transient_service_failures_recover_without_manual_refresh(self):
        done = threading.Event()
        results, calls = [], []
        def fetch(url):
            calls.append(url)
            if len(calls) <= 2:
                raise OSError('temporary test connection failure')
            return fixture()
        def publish(result):
            results.append(result)
            if result['state'] in ('synced', 'error'):done.set()
        with tempfile.TemporaryDirectory(prefix='caelestia-lyrics-test-') as directory:
            worker = LyricsWorker(publish, directory, fetch=fetch, retry_delays=(.01,.02))
            try:
                worker.request(dict(available=True, trackId='test', title='Test song', artist='Sample artist', duration=180))
                self.assertTrue(done.wait(2))
                self.assertEqual(len(calls), 3)
                self.assertEqual(results[-1]['state'], 'synced')
                self.assertFalse(any(item['state']=='error' for item in results))
            finally:
                worker.stop()

    def test_429_and_server_errors_retry_but_other_4xx_do_not(self):
        for status, expected_calls, expected_state in ((429,2,'synced'), (503,2,'synced'), (403,1,'error')):
            with self.subTest(status=status), tempfile.TemporaryDirectory(prefix='caelestia-lyrics-test-') as directory:
                calls, results, done = [], [], threading.Event()
                def fetch(url):
                    calls.append(url)
                    if len(calls)==1:raise HttpStatusError(status)
                    return fixture()
                def publish(result):
                    results.append(result)
                    if result['state'] in ('synced','error'):done.set()
                worker = LyricsWorker(publish, directory, fetch=fetch, retry_delays=(.01,.02))
                try:
                    worker.request(dict(available=True, trackId='test', title='Test song', artist='Sample artist', duration=180))
                    self.assertTrue(done.wait(2))
                    self.assertEqual(len(calls), expected_calls)
                    self.assertEqual(results[-1]['state'], expected_state)
                finally:
                    worker.stop()

    def test_retry_exhaustion_is_bounded_to_three_attempts(self):
        calls, results, done = [], [], threading.Event()
        def fetch(url):
            calls.append(url)
            raise HttpStatusError(500)
        def publish(result):
            results.append(result)
            if result['state']=='error':done.set()
        with tempfile.TemporaryDirectory(prefix='caelestia-lyrics-test-') as directory:
            worker = LyricsWorker(publish, directory, fetch=fetch, retry_delays=(.01,.02))
            try:
                worker.request(dict(available=True, trackId='test', title='Test song', artist='Sample artist', duration=180))
                self.assertTrue(done.wait(2))
                self.assertEqual(len(calls), 3)
                self.assertEqual([item['state'] for item in results], ['loading','error'])
                self.assertEqual(results[-1]['trackKey'], 'test')
            finally:
                worker.stop()

    def test_track_change_aborts_old_retry_wait_and_publishes_only_new_result(self):
        failed, done = threading.Event(), threading.Event()
        results, old_calls = [], []
        def fetch(url):
            title = parse_qs(urlsplit(url).query)['track_name'][0]
            if title=='Old test':
                old_calls.append(url)
                failed.set()
                raise OSError('temporary old-track error')
            return fixture(title=title)
        def publish(result):
            results.append(result)
            if result['trackKey']=='new' and result['state']=='synced':done.set()
        with tempfile.TemporaryDirectory(prefix='caelestia-lyrics-test-') as directory:
            worker = LyricsWorker(publish, directory, fetch=fetch, retry_delays=(1,3))
            try:
                worker.request(dict(available=True, trackId='old', title='Old test', artist='Sample artist', duration=180))
                self.assertTrue(failed.wait(2))
                worker.request(dict(available=True, trackId='new', title='New test', artist='Sample artist', duration=180))
                self.assertTrue(done.wait(2))
                self.assertEqual(len(old_calls), 1)
                self.assertFalse(any(item['trackKey']=='old' and item['state'] in ('error','synced') for item in results))
            finally:
                worker.stop()

    def test_stop_wakes_pending_retry_without_additional_service_calls(self):
        failed = threading.Event()
        calls = []
        def fetch(url):
            calls.append(url)
            failed.set()
            raise OSError('temporary test failure')
        with tempfile.TemporaryDirectory(prefix='caelestia-lyrics-test-') as directory:
            worker = LyricsWorker(lambda value:None, directory, fetch=fetch, retry_delays=(1,3))
            worker.request(dict(available=True, trackId='test', title='Test song', artist='Sample artist', duration=180))
            self.assertTrue(failed.wait(2))
            worker.stop()
            self.assertFalse(worker._thread.is_alive())
            self.assertEqual(len(calls), 1)


if __name__=='__main__':unittest.main(verbosity=2)
