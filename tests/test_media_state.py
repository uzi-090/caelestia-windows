"""Regression tests for infrequent Windows media snapshots and transitions."""
from pathlib import Path
import datetime as dt
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from media_state import (ArtworkTransition, MetadataTransition, StableSessionIds,
                         TimelineAnchor, choose_session, utc_timestamp)

WALL = 1_780_000_000.0


def stamp(offset=0):
    return dt.datetime.fromtimestamp(WALL + offset, dt.timezone.utc)


def observe(clock, now=0, **changes):
    values = dict(track_id='track', position=0, duration=300, playing=True,
                  rate=1, updated=stamp(), now=now, wall_now=WALL + now)
    values.update(changes)
    return clock.observe(**values)


class TimelineTests(unittest.TestCase):
    def test_stale_snapshot_advances_past_five_seconds(self):
        clock = TimelineAnchor()
        for now in (0, 1, 5, 10, 20, 90):
            self.assertAlmostEqual(observe(clock, now), now)

    def test_same_position_with_fresh_timestamp_does_not_freeze(self):
        clock = TimelineAnchor()
        for now in range(21):
            self.assertAlmostEqual(observe(clock, now, updated=stamp(now)), now)

    def test_missing_timestamp_uses_monotonic_clock(self):
        clock = TimelineAnchor()
        for now in (0, 4, 6, 20):
            self.assertEqual(observe(clock, now, updated=None), now)

    def test_old_initial_snapshot_is_projected_without_five_second_cap(self):
        clock = TimelineAnchor()
        self.assertEqual(observe(clock, now=20, position=10), 30)

    def test_pause_resume_excludes_paused_time_with_stale_snapshot(self):
        clock = TimelineAnchor()
        observe(clock)
        self.assertEqual(observe(clock, 10, playing=False), 10)
        self.assertEqual(observe(clock, 40, playing=False), 10)
        self.assertEqual(observe(clock, 50, playing=True), 10)
        self.assertEqual(observe(clock, 60, playing=True), 20)

    def test_provider_position_change_reanchors_even_with_stale_timestamp(self):
        clock = TimelineAnchor()
        observe(clock)
        self.assertEqual(observe(clock, 10, position=80), 80)
        self.assertEqual(observe(clock, 20, position=80), 90)

    def test_external_seek_and_new_timestamp_reanchor(self):
        clock = TimelineAnchor()
        observe(clock)
        self.assertEqual(observe(clock, 20, position=150, updated=stamp(20)), 150)
        self.assertEqual(observe(clock, 25, position=150, updated=stamp(20)), 155)

    def test_accepted_seek_is_not_undone_by_stale_provider(self):
        clock = TimelineAnchor()
        observe(clock)
        clock.seek(100, 10)
        self.assertEqual(observe(clock, 11), 101)
        self.assertEqual(observe(clock, 20), 110)
        self.assertEqual(observe(clock, 21, position=111, updated=stamp(21)), 111)

    def test_accepted_seek_ignores_late_pre_seek_progress_update(self):
        clock = TimelineAnchor()
        observe(clock)
        clock.seek(100, 10)
        self.assertEqual(observe(clock, 11, position=1, updated=stamp(11)), 101)
        self.assertEqual(observe(clock, 12, position=102, updated=stamp(12)), 102)
        self.assertEqual(observe(clock, 13, position=102, updated=stamp(12)), 103)

    def test_rate_changes_preserve_position_and_zero_is_not_one(self):
        clock = TimelineAnchor()
        observe(clock)
        self.assertEqual(observe(clock, 10, rate=2), 10)
        self.assertEqual(observe(clock, 15, rate=0), 20)
        self.assertEqual(observe(clock, 25, rate=0), 20)

    def test_end_clamp_and_unknown_duration(self):
        clock = TimelineAnchor()
        observe(clock)
        self.assertEqual(observe(clock, 400), 300)
        clock = TimelineAnchor()
        observe(clock, duration=0)
        self.assertEqual(observe(clock, 400, duration=0), 400)

    def test_new_track_does_not_inherit_unchanged_old_timeline(self):
        clock = TimelineAnchor()
        observe(clock, position=100)
        self.assertEqual(observe(clock, 2, track_id='new', position=100), 0)
        self.assertEqual(observe(clock, 3, track_id='new', position=1, updated=stamp(3)), 1)

    def test_first_metadata_does_not_restart_existing_playback(self):
        clock = TimelineAnchor()
        observe(clock, position=100, track_id='')
        self.assertEqual(observe(clock, 1, position=100), 101)

    def test_wall_clock_adjustment_does_not_break_existing_anchor(self):
        clock = TimelineAnchor()
        observe(clock)
        self.assertEqual(observe(clock, 20, wall_now=WALL+3600), 20)

    def test_datetime_and_ticks_and_invalid_epoch(self):
        self.assertEqual(utc_timestamp(stamp()), WALL)
        self.assertEqual(utc_timestamp(stamp().replace(tzinfo=None)), WALL)
        self.assertEqual(utc_timestamp(int((WALL+11_644_473_600)*10_000_000)), WALL)
        self.assertIsNone(utc_timestamp(0))
        self.assertIsNone(utc_timestamp(None))


class MetadataTests(unittest.TestCase):
    def policy(self):
        return MetadataTransition('chrome::1', 'Google Chrome')

    def test_autoplay_placeholder_is_bridged_then_real_track_replaces(self):
        policy = self.policy()
        policy.observe(dict(title='First', artist='Artist'), 0)
        first = policy.track_id
        self.assertFalse(policy.observe(dict(title='A site is playing media'), 1))
        self.assertEqual(policy.value['title'], 'First')
        self.assertTrue(policy.pending)
        self.assertTrue(policy.observe(dict(title='Second', artist='Artist'), 1.5))
        self.assertNotEqual(policy.track_id, first)
        self.assertEqual(policy.value['title'], 'Second')
        self.assertFalse(policy.pending)

    def test_placeholder_cannot_keep_wrong_track_forever(self):
        policy = self.policy()
        policy.observe(dict(title='First', artist='Artist'), 0)
        policy.observe(dict(title='Google Chrome'), 1)
        self.assertTrue(policy.observe(dict(title='Google Chrome'), 3.1))
        self.assertEqual(policy.track_id, '')
        self.assertEqual(policy.value['title'], 'Waiting for track information')

    def test_missing_thumbnail_does_not_change_track_identity(self):
        policy = self.policy()
        policy.observe(dict(title='Song', artist='Artist', album='Album'), 0)
        key = policy.track_id
        self.assertFalse(policy.observe(dict(title='Song', artist='Artist', album='Album'), 8))
        self.assertEqual(key, policy.track_id)

    def test_brief_artist_dropout_preserves_identity(self):
        policy = self.policy()
        policy.observe(dict(title='Song', artist='Artist'), 0)
        key = policy.track_id
        policy.observe(dict(title='Song'), 1)
        policy.observe(dict(title='Song', artist='Artist'), 1.5)
        self.assertEqual(policy.track_id, key)
        self.assertFalse(policy.pending)

    def test_missing_artist_is_not_retained_indefinitely(self):
        policy = self.policy()
        policy.observe(dict(title='Song', artist='Artist'), 0)
        policy.observe(dict(title='Song'), 1)
        policy.observe(dict(title='Song'), 4)
        self.assertEqual(policy.value['artist'], '')

    def test_browser_title_with_real_artist_is_not_placeholder(self):
        policy = self.policy()
        policy.observe(dict(title='Chrome', artist='Real artist'), 0)
        self.assertTrue(policy.track_id)


class ArtworkTests(unittest.TestCase):
    def offer(self, art, digest='a', width=300, height=300, **changes):
        values = dict(digest=digest, url='file:///'+digest+'.png', width=width,
                      height=height, generic=False, known_logos=set())
        values.update(changes)
        return art.accept(**values)

    def test_late_artwork_and_higher_quality_revision_are_accepted(self):
        art = ArtworkTransition()
        art.set_track('track')
        self.assertEqual(art.url, '')
        self.assertTrue(self.offer(art, width=64, height=64))
        self.assertTrue(self.offer(art, digest='high', width=1024, height=1024))
        self.assertEqual(art.url, 'file:///high.png')
        self.assertEqual(art.width, 1024)

    def test_generic_logo_does_not_overwrite_good_cover(self):
        art = ArtworkTransition()
        art.set_track('track')
        self.offer(art)
        self.assertFalse(self.offer(art, digest='logo', generic=True))
        self.assertFalse(self.offer(art, digest='logo', known_logos={'logo'}))
        self.assertEqual(art.digest, 'a')

    def test_low_resolution_update_cannot_downgrade_same_track(self):
        art = ArtworkTransition()
        art.set_track('track')
        self.offer(art)
        self.assertFalse(self.offer(art, digest='small', width=32, height=32))
        self.assertEqual(art.width, 300)

    def test_new_track_clears_old_cover_until_current_thumbnail_arrives(self):
        art = ArtworkTransition()
        art.set_track('first')
        self.offer(art)
        art.set_track('second')
        self.assertEqual(art.url, '')
        self.assertEqual(art.width, 0)
        self.assertTrue(self.offer(art, digest='second'))


class SessionTests(unittest.TestCase):
    def test_reorder_does_not_change_ids_or_user_selection(self):
        registry = StableSessionIds()
        a, b, c = object(), object(), object()
        first = registry.update([('Chrome', a), ('VLC', b), ('Chrome', c)])
        second = registry.update([('Chrome', c), ('Chrome', a), ('VLC', b)])
        self.assertEqual(dict((obj, sid) for sid, obj in first),
                         dict((obj, sid) for sid, obj in second))

    def test_unique_app_reconnection_preserves_selection_id(self):
        registry = StableSessionIds()
        first = registry.update([('VLC', object())])[0][0]
        self.assertEqual(registry.update([('VLC', object())])[0][0], first)

    def test_real_active_media_beats_browser_placeholder(self):
        items = [dict(id='browser', playing=True, realMetadata=False),
                 dict(id='music', playing=True, realMetadata=True)]
        self.assertEqual(choose_session(items, '', 'browser', 'browser'), 'music')

    def test_explicit_selection_is_honoured_while_session_exists(self):
        items = [dict(id='browser', playing=False, realMetadata=False),
                 dict(id='music', playing=True, realMetadata=True)]
        self.assertEqual(choose_session(items, 'browser', 'music', 'music'), 'browser')
        self.assertEqual(choose_session(items, 'gone', 'music', ''), 'music')

    def test_active_generic_player_beats_paused_old_track(self):
        items = [dict(id='browser', playing=True, realMetadata=False),
                 dict(id='music', playing=False, realMetadata=True)]
        self.assertEqual(choose_session(items, '', 'music', 'music'), 'browser')


if __name__ == '__main__':
    unittest.main()
