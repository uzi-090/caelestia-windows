"""Mocked Windows media integration; never controls a real player."""
import asyncio
import datetime as dt
import io
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QCoreApplication
from PIL import Image
import backend
from backend import Backend, _MediaSession, _read_media_thumbnail
import winrt.windows.media.control as control
import winrt.windows.storage.streams as streams

APP = QCoreApplication.instance() or QCoreApplication([])


class EventSource:
    def __init__(self):
        self.handlers = {}

    def __getattr__(self, name):
        if name.startswith('add_'):
            def add(handler):
                self.handlers[name[4:]] = handler
                return name[4:]
            return add
        if name.startswith('remove_'):
            return lambda token: self.handlers.pop(token, None)
        raise AttributeError(name)

    def fire(self, event):
        self.handlers[event](self, None)


class FakeSession(EventSource):
    source_app_user_model_id = 'chrome.exe'

    def __init__(self):
        super().__init__()
        self.props = SimpleNamespace(title='First song', artist='Artist', album_title='Album',
                                     track_number=1, album_track_count=3, thumbnail=None)
        self.playback = SimpleNamespace(
            playback_status=control.GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING,
            playback_rate=1.0, auto_repeat_mode=None, is_shuffle_active=False,
            controls=SimpleNamespace(**{key: True for key in (
                'is_play_pause_toggle_enabled', 'is_play_enabled', 'is_pause_enabled',
                'is_next_enabled', 'is_previous_enabled', 'is_playback_position_enabled',
                'is_shuffle_enabled', 'is_repeat_enabled')}))
        self.timeline = SimpleNamespace(start_time=dt.timedelta(),
                                        end_time=dt.timedelta(seconds=300),
                                        position=dt.timedelta(),
                                        last_updated_time=dt.datetime.now(dt.timezone.utc))
        self.seek = AsyncMock(return_value=True)

    async def try_get_media_properties_async(self):
        return self.props

    def get_playback_info(self):
        return self.playback

    def get_timeline_properties(self):
        return self.timeline

    async def try_change_playback_position_async(self, ticks):
        return await self.seek(ticks)


class MediaBackendTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cache = patch.object(backend, 'CACHE', Path(self.temp.name))
        self.cache.start()
        self.value = Backend(start_workers=False)
        self.session = FakeSession()
        self.record = _MediaSession('chrome::stable', self.session)

    def tearDown(self):
        self.value.stop()
        self.cache.stop()
        self.temp.cleanup()

    async def test_thumbnail_late_arrival_and_revision_get_new_native_content_url(self):
        await self.value._refresh_media_properties(self.record, 0, True, {})
        key = self.record.metadata.track_id
        self.assertTrue(key)
        self.assertEqual(self.record.artwork.url, '')
        self.session.props.thumbnail = object()
        with patch.object(backend, '_read_media_thumbnail', AsyncMock(return_value=(b'original-native-image', 'png', 600, 600))):
            await self.value._refresh_media_properties(self.record, 0, True, {})
        first = self.record.artwork.url
        self.assertTrue(first.endswith('.png'))
        self.assertEqual(Path(first.removeprefix('file:///')).read_bytes(), b'original-native-image')
        with patch.object(backend, '_read_media_thumbnail', AsyncMock(return_value=(b'better-native-image', 'png', 1200, 1200))):
            await self.value._refresh_media_properties(self.record, 0, True, {})
        self.assertNotEqual(first, self.record.artwork.url)
        self.assertEqual(key, self.record.metadata.track_id)
        self.assertEqual(self.record.artwork.width, 1200)

    async def test_stale_async_metadata_is_rejected_after_new_event(self):
        gate = asyncio.Event()
        async def delayed():
            await gate.wait()
            return self.session.props
        self.session.try_get_media_properties_async = delayed
        task = asyncio.create_task(self.value._refresh_media_properties(self.record, 0, False, {}))
        await asyncio.sleep(0)
        self.record.revision += 1
        gate.set()
        await task
        self.assertEqual(self.record.metadata.track_id, '')
        self.assertTrue(self.record.metadata_dirty)

    async def test_accepted_seek_includes_provider_start_and_updates_clock(self):
        self.record.start, self.record.duration = 100, 300
        self.record.clock.observe(track_id='song', position=0, duration=300, playing=False,
                                  rate=1, updated=None, now=1, wall_now=1)
        await self.value._run_media_command(self.record, 'seek', 20)
        self.session.seek.assert_awaited_once_with(1_200_000_000)
        self.assertEqual(self.record.clock.position(1), 20)

    async def test_rejected_seek_does_not_move_clock(self):
        self.session.seek.return_value = False
        await self.value._run_media_command(self.record, 'seek', 20)
        self.assertEqual(self.record.clock.position(1), 0)

    async def test_properties_events_update_without_real_playback_and_unregister(self):
        session = self.session
        class Manager(EventSource):
            @classmethod
            async def request_async(cls):
                return manager
            def get_sessions(self):
                return [session]
            def get_current_session(self):
                return session
        manager = Manager()
        async def wait_title(title):
            for _ in range(100):
                if self.value.data['media']['title'] == title:
                    return
                await asyncio.sleep(.01)
            self.fail('Event-driven metadata did not publish '+title)
        with patch.object(control, 'GlobalSystemMediaTransportControlsSessionManager', Manager):
            task = asyncio.create_task(self.value._media_main())
            try:
                await wait_title('First song')
                stable = self.value.data['media']['sessionId']
                session.props.title = 'Autoplay next song'
                session.fire('media_properties_changed')
                await wait_title('Autoplay next song')
                self.assertEqual(stable, self.value.data['media']['sessionId'])
                self.assertIn('timeline_properties_changed', session.handlers)
                self.assertIn('sessions_changed', manager.handlers)
            finally:
                self.value._stop_event.set()
                self.value._wake_media()
                await asyncio.wait_for(task, 2)
        self.assertEqual(session.handlers, {})
        self.assertEqual(manager.handlers, {})

    async def test_thumbnail_reader_rejects_truncation_and_keeps_original_pixels(self):
        buffer = io.BytesIO()
        Image.new('RGB', (1024, 768), '#7f3a62').save(buffer, format='PNG')
        native = buffer.getvalue()
        class Stream:
            size = len(native)
            def close(self):
                pass
        class Thumbnail:
            async def open_read_async(self):
                return Stream()
        class Reader:
            def __init__(self, stream):
                self.offset = self.loaded = 0
            async def load_async(self, wanted):
                self.loaded = min(wanted, 31, len(native)-self.offset)
                return self.loaded
            def read_bytes(self, block):
                block[:] = native[self.offset:self.offset+len(block)]
                self.offset += len(block)
            def close(self):
                pass
        with patch.object(streams, 'DataReader', Reader):
            contents, extension, width, height = await _read_media_thumbnail(Thumbnail())
            self.assertEqual((contents, extension, width, height), (native, 'png', 1024, 768))
        class TruncatedReader(Reader):
            async def load_async(self, wanted):
                return 0
        with patch.object(streams, 'DataReader', TruncatedReader):
            self.assertIsNone(await _read_media_thumbnail(Thumbnail()))

    async def test_fresh_provider_wrappers_preserve_cover_and_advancing_clock(self):
        wrappers = []
        class Manager(EventSource):
            @classmethod
            async def request_async(cls):
                return manager
            def get_sessions(self):
                value = FakeSession()
                value.props.thumbnail = object()
                wrappers.append(value)
                return [value]
            def get_current_session(self):
                return wrappers[-1]
        manager = Manager()
        async def wait_for(predicate):
            for _ in range(100):
                if predicate():
                    return
                await asyncio.sleep(.01)
            self.fail('Provider wrapper refresh did not complete')
        with patch.object(control, 'GlobalSystemMediaTransportControlsSessionManager', Manager), \
                patch.object(backend, '_read_media_thumbnail', AsyncMock(return_value=(b'native-cover', 'png', 600, 600))):
            task = asyncio.create_task(self.value._media_main())
            try:
                await wait_for(lambda: bool(self.value.data['media']['artwork']))
                original = dict(self.value.data['media'])
                # Move beyond zero so recreating a clock is observable.
                await asyncio.sleep(.05)
                self.value._wake_media()
                await wait_for(lambda: self.value.data['media']['position'] > original['position']+.02)
                before = dict(self.value.data['media'])
                manager.fire('sessions_changed')
                await wait_for(lambda: len(wrappers) == 2)
                self.assertEqual(self.value.data['media']['sessionId'], original['sessionId'])
                self.assertEqual(self.value.data['media']['trackId'], original['trackId'])
                self.assertEqual(self.value.data['media']['artwork'], original['artwork'])
                self.assertGreaterEqual(self.value.data['media']['position'], before['position'])
                self.assertEqual(wrappers[0].handlers, {})
                self.assertIn('timeline_properties_changed', wrappers[1].handlers)
            finally:
                self.value._stop_event.set()
                self.value._wake_media()
                await asyncio.wait_for(task, 2)


if __name__ == '__main__':
    unittest.main()
