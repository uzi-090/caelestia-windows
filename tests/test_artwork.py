"""Strict artwork matching and asynchronous merge tests; all HTTP is mocked."""
from pathlib import Path
import io
import json
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PySide6.QtCore import QCoreApplication
import artwork
from artwork import (ArtworkWorker, candidate_releases, contact_user_agent, decode_artwork,
                     matching_candidate, merge_artwork, music_query, source_url)
import backend
from backend import Backend

APP = QCoreApplication.instance() or QCoreApplication([])
RELEASE = '76df3287-6cda-33eb-8e9a-044b5e15ffdd'


def media(key='song1', **changes):
    result = dict(available=True, trackId=key, sessionId='Chrome::1', metadataPending=False,
                  title='Song', artist='Artist', album='Album', duration=260,
                  artwork='file:///native.jpg', artworkWidth=150, artworkHeight=83)
    result.update(changes)
    return result


def recording(**changes):
    result = dict(title='Song', length=260000, video=False,
                  **{'artist-credit': [{'name': 'Artist', 'artist': {'name': 'Artist'}}],
                     'releases': [{'id': RELEASE, 'title': 'Album', 'status': 'Official'}]})
    result.update(changes)
    return result


def cover_bytes(size=(500, 500)):
    buffer = io.BytesIO()
    Image.new('RGB', size, '#34517d').save(buffer, format='PNG')
    return buffer.getvalue()


class ArtworkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.publish = Mock()
        self.fetch = Mock(return_value={'recordings': [recording()]})
        self.download = Mock(return_value=cover_bytes())
        self.worker = ArtworkWorker(self.publish, self.path, fetch=self.fetch, download=self.download,
                                    contact_email='test@example.org', autostart=False, min_interval=0)

    def tearDown(self):
        self.worker.stop()
        self.temp.cleanup()

    def test_private_placeholder_pending_and_missing_artist_are_not_queried(self):
        for value in (media(metadataPending=True), media(artist=''), media(duration=0),
                      media(title='A site is playing media'), media(artist='YouTube'),
                      media(trackId=''), media(artworkWidth=1000, artworkHeight=1000)):
            self.assertIsNone(music_query(value))
        self.assertIsNotNone(music_query(media()))

    def test_exact_artist_title_duration_matching_rejects_wrong_recordings(self):
        query = music_query(media())
        self.assertTrue(matching_candidate(recording(), query))
        self.assertFalse(matching_candidate(recording(title='Song Remix'), query))
        self.assertFalse(matching_candidate(recording(length=290000), query))
        self.assertFalse(matching_candidate(recording(video=True), query))
        self.assertFalse(matching_candidate(recording(**{'artist-credit': [{'name': 'Other'}]}), query))

    def test_album_must_match_when_known_and_release_uuid_is_validated(self):
        query = music_query(media())
        self.assertEqual(candidate_releases(recording(), query), [RELEASE])
        self.assertEqual(candidate_releases(recording(releases=[{'id': RELEASE, 'title': 'Wrong album'}]), query), [])
        self.assertEqual(candidate_releases(recording(releases=[{'id': '../../outside', 'title': 'Album'}]), query), [])

    def test_source_url_only_accepts_musicbrainz_release_pages(self):
        self.assertEqual(source_url('https://musicbrainz.org/release/'+RELEASE),
                         'https://musicbrainz.org/release/'+RELEASE)
        self.assertEqual(source_url('https://musicbrainz.org.evil/release/'+RELEASE), '')
        self.assertEqual(source_url('https://musicbrainz.org/release/not-an-id'), '')
        self.assertEqual(source_url('http://musicbrainz.org/release/'+RELEASE), '')

    def test_contact_is_required_and_invalid_header_content_is_rejected(self):
        self.assertEqual(contact_user_agent(self.path), '')
        for email in ('', 'not an email', 'x@example.org\r\nEvil: header', 'http://example.org'):
            self.assertEqual(contact_user_agent(self.path, email), '')
        (self.path/'artwork-contact.json').write_text(json.dumps({'contactEmail': 'test@example.org'}))
        self.assertIn('test@example.org', contact_user_agent(self.path))

    def test_default_disabled_worker_cannot_make_external_request(self):
        value = ArtworkWorker(Mock(), self.path, fetch=self.fetch, download=self.download, autostart=True)
        try:
            self.assertFalse(value.enabled)
            self.assertFalse(value._thread.is_alive())
            value.request(media())
            self.assertTrue(value._queue.empty())
            self.assertIsNone(value._load_track(music_query(media())))
            self.fetch.assert_not_called()
        finally:
            value.stop()

    def test_native_download_bytes_are_saved_once_and_success_cache_is_reused(self):
        result = self.worker._load_track(music_query(media()))
        self.assertEqual((result['artworkWidth'], result['artworkHeight']), (500, 500))
        self.assertEqual((self.path/result['file']).read_bytes(), self.download.return_value)
        self.assertEqual(result['artworkSource'], 'Cover Art Archive')
        self.download.assert_called_once_with('https://coverartarchive.org/release/'+RELEASE+'/front-500',
                                              max_bytes=3*1024*1024, accept='image/*',
                                              user_agent='CaelestiaWindows/1.0 (test@example.org)')
        again = self.worker._load_track(music_query(media()))
        self.assertEqual(again['artwork'], result['artwork'])
        self.fetch.assert_called_once()
        self.assertIn('dur%3A%5B', self.fetch.call_args[0][0])

    def test_negative_results_are_cached(self):
        self.fetch.return_value = {'recordings': []}
        self.assertIsNone(self.worker._load_track(music_query(media())))
        self.assertIsNone(self.worker._load_track(music_query(media())))
        self.fetch.assert_called_once()
        self.download.assert_not_called()

    def test_latest_track_queue_coalesces_and_old_result_is_rejected(self):
        self.worker.request(media('old'))
        old_generation = self.worker._generation
        self.worker.request(media('new', title='New song'))
        generation, key, track, force = self.worker._queue.get_nowait()
        self.assertEqual(key, 'new')
        self.assertEqual(track['title'], 'New song')
        self.worker._publish(old_generation, {'trackId': 'old'})
        self.publish.assert_not_called()
        self.worker._publish(generation, {'trackId': 'new'})
        self.publish.assert_called_once_with({'trackId': 'new'})

    def test_no_image_download_after_track_changes_during_search(self):
        current = Mock(side_effect=[True, False])
        self.assertIsNone(self.worker._load_track(music_query(media()), still_current=current))
        self.download.assert_not_called()

    def test_decoder_rejects_small_corrupt_or_oversized_images(self):
        self.assertEqual(decode_artwork(cover_bytes()), ('png', 500, 500))
        self.assertIsNone(decode_artwork(cover_bytes((150, 83))))
        self.assertIsNone(decode_artwork(b'not an image'))
        self.assertIsNone(decode_artwork(b'x'*(3*1024*1024+1)))

    def test_sparse_query_rate_limiter_waits_before_second_search(self):
        self.worker._min_interval = 3.1
        self.fetch.return_value = {'recordings': []}
        self.worker._stop.wait = Mock(return_value=False)
        with patch.object(artwork.time, 'monotonic', side_effect=[100, 100, 100.2, 103.1]):
            self.worker._load_track(music_query(media()), force=True)
            self.worker._load_track(music_query(media()), force=True)
        self.assertAlmostEqual(self.worker._stop.wait.call_args.args[0], 2.9)

    def test_merge_never_downgrades_native_or_applies_wrong_track(self):
        result = {**self.worker._load_track(music_query(media())), 'trackId': 'song1'}
        self.assertEqual(merge_artwork(media(), result)['artworkWidth'], 500)
        self.assertEqual(merge_artwork(media(artworkWidth=1000, artworkHeight=1000), result)['artwork'], 'file:///native.jpg')
        self.assertEqual(merge_artwork(media('new'), result)['artwork'], 'file:///native.jpg')

    def test_backend_override_survives_native_snapshots_and_clears_on_track_change(self):
        with patch.object(backend, 'CACHE', self.path):
            value = Backend(start_workers=False)
        value._artwork_worker = Mock(current_key='song1')
        try:
            value._apply_part('media', media())
            result = {**self.worker._load_track(music_query(media())), 'trackId': 'song1'}
            value._apply_part('HQcover', result)
            enriched = value.data['media']['artwork']
            self.assertNotEqual(enriched, 'file:///native.jpg')
            value._apply_part('media', media(position=12))
            self.assertEqual(value.data['media']['artwork'], enriched)
            self.assertEqual(value.data['media']['position'], 12)
            value._apply_part('media', media('new'))
            self.assertEqual(value.data['media']['artwork'], 'file:///native.jpg')
            value._apply_part('HQcover', result)
            self.assertEqual(value.data['media']['artwork'], 'file:///native.jpg')
        finally:
            value.stop()


if __name__ == '__main__':
    unittest.main()
