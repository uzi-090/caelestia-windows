"""Provider-independent media clock and transition rules.

Windows publishes a timeline snapshot, not a continuously advancing position.
These rules keep one monotonic clock for both dashboard pages without requiring
the player to publish fresh metadata or a new timestamp every second.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import math
from typing import Any


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError, OverflowError):
        return default


def utc_timestamp(value: Any) -> float | None:
    """Accept PyWinRT datetime and older DateTime/tick projections.

    An unset WinRT timestamp is 1601, and cannot anchor a playback clock.
    Naive values returned by a provider are interpreted as the API's UTC time.
    """
    try:
        if isinstance(value, dt.datetime):
            result = value.replace(tzinfo=dt.timezone.utc) if value.tzinfo is None else value
            stamp = result.timestamp()
        else:
            ticks = getattr(value, "universal_time", value)
            stamp = _finite(ticks, -1) / 10_000_000 - 11_644_473_600
        return stamp if math.isfinite(stamp) and stamp >= 946_684_800 else None
    except (TypeError, ValueError, OverflowError, OSError):
        return None


class TimelineAnchor:
    def __init__(self) -> None:
        self.track_id = ""
        self.duration = 0.0
        self.start = 0.0
        self._position = 0.0
        self._at = 0.0
        self._playing = False
        self._rate = 1.0
        self._sample: tuple[float, float | None] | None = None
        self._initialised = False
        self._seek_until = 0.0

    def position(self, now: float) -> float:
        elapsed = max(0.0, now - self._at) if self._playing else 0.0
        result = max(0.0, self._position + elapsed * self._rate)
        return min(result, self.duration) if self.duration > 0 else result

    def observe(self, *, track_id: str, position: float, duration: float,
                playing: bool, rate: float | None, updated: Any,
                now: float, wall_now: float, start: float = 0.0) -> float:
        raw = max(0.0, _finite(position))
        stamp = utc_timestamp(updated)
        # Future/ancient timestamps are unusable, but a valid old snapshot must
        # continue advancing for more than five seconds.
        if stamp is not None and not -1.0 <= wall_now - stamp <= 86_400:
            stamp = None
        sample = (raw, stamp)
        speed = _finite(rate, 1.0) if rate is not None else 1.0
        old_position = self.position(now)
        changed_track = self._initialised and bool(self.track_id) and track_id != self.track_id
        # Some providers refresh LastUpdatedTime without updating Position.
        # A new timestamp alone must not pull the local clock back every poll.
        changed_sample = self._sample is None or raw != self._sample[0]
        if changed_track:
            self._seek_until = 0.0
        elif self._seek_until:
            if abs(raw - old_position) <= 2.0:
                self._seek_until = 0.0  # Provider acknowledged the accepted seek.
            elif now <= self._seek_until:
                changed_sample = False  # Ignore an in-flight pre-seek update.
            else:
                self._seek_until = 0.0
        if not self._initialised:
            anchored = raw
            if playing and stamp is not None:
                anchored += max(0.0, wall_now - stamp) * speed
        elif changed_track:
            # Metadata can arrive before the new timeline. Never carry the
            # previous track's unchanged position into a new track.
            anchored = raw if changed_sample else 0.0
            if changed_sample and playing and stamp is not None:
                anchored += max(0.0, wall_now - stamp) * speed
        elif changed_sample:
            anchored = raw
            # A provider may update Position but leave LastUpdatedTime stale.
            # In that case this is a fresh sample received now, not an old one.
            if playing and stamp is not None and (self._sample is None or stamp != self._sample[1]):
                anchored += max(0.0, wall_now - stamp) * speed
        else:
            # Includes pause/resume/rate changes with an unchanged provider
            # snapshot. Rebasing the current projection excludes paused time.
            anchored = old_position
        self.track_id = track_id
        self.duration = max(0.0, _finite(duration))
        self.start = max(0.0, _finite(start))
        self._position = max(0.0, anchored)
        if self.duration:
            self._position = min(self._position, self.duration)
        self._at, self._playing, self._rate = now, bool(playing), speed
        self._sample, self._initialised = sample, True
        return self.position(now)

    def seek(self, position: float, now: float) -> None:
        self._position = max(0.0, _finite(position))
        if self.duration:
            self._position = min(self._position, self.duration)
        self._at = now
        self._seek_until = now + 2.0
        # Preserve the provider sample: repeated stale snapshots cannot undo
        # an accepted seek before the player publishes its updated timeline.


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def metadata_is_generic(value: dict[str, Any], app_name: str) -> bool:
    title = clean_text(value.get("title")).casefold()
    if not title:
        return True
    defaults = {"unknown title", "nothing playing", "media player", app_name.casefold()}
    if app_name in {"Google Chrome", "Microsoft Edge", "Firefox", "Brave", "Opera"}:
        defaults.update({"chrome", "google chrome", "chrome.exe", "msedge.exe",
                         "microsoft edge", "firefox", "brave", "opera",
                         "a site is playing media", "a website is playing media"})
    return title in defaults and not clean_text(value.get("artist")) and not clean_text(value.get("album"))


class MetadataTransition:
    """Briefly bridge provider placeholders; never keep an old track forever."""
    def __init__(self, session_id: str, app_name: str, grace: float = 2.0) -> None:
        self.session_id, self.app_name, self.grace = session_id, app_name, grace
        self.value: dict[str, Any] = {}
        self.track_id = ""
        self.pending = True
        self._pending_since: float | None = None

    def observe(self, raw: dict[str, Any], now: float) -> bool:
        candidate = {"title": clean_text(raw.get("title")),
                     "artist": clean_text(raw.get("artist")),
                     "album": clean_text(raw.get("album")),
                     "trackNumber": int(raw.get("trackNumber") or 0),
                     "albumTrackCount": int(raw.get("albumTrackCount") or 0)}
        generic = metadata_is_generic(candidate, self.app_name)
        incomplete_same = bool(self.value and candidate["title"] == self.value.get("title")
                               and any(self.value.get(key) and not candidate.get(key)
                                       for key in ("artist", "album")))
        if generic or incomplete_same:
            if self._pending_since is None:
                self._pending_since = now
            self.pending = True
            if self.track_id and now - self._pending_since < self.grace:
                return False
        else:
            self._pending_since = None
            self.pending = False
        if generic:
            candidate.update(title="Waiting for track information", artist="", album="")
            identity = ""
        else:
            payload = "\x1f".join((self.session_id, candidate["title"], candidate["artist"],
                                     candidate["album"], str(candidate["trackNumber"])))
            identity = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
        changed = identity != self.track_id
        self.value, self.track_id = candidate, identity
        return changed


class ArtworkTransition:
    def __init__(self) -> None:
        self.track_id = ""
        self.url = ""
        self.digest = ""
        self.width = self.height = 0

    def set_track(self, track_id: str) -> None:
        if track_id != self.track_id:
            self.track_id = track_id
            self.url = self.digest = ""
            self.width = self.height = 0

    def accept(self, *, digest: str, url: str, width: int, height: int,
               generic: bool, known_logos: set[str]) -> bool:
        if not self.track_id or generic or digest in known_logos:
            return False
        if self.digest and width * height < self.width * self.height:
            return False  # A late application icon must not downgrade a cover.
        changed = digest != self.digest
        self.digest, self.url, self.width, self.height = digest, url, width, height
        return changed


class StableSessionIds:
    """IDs survive provider order changes and unique-app COM reconnections."""
    def __init__(self) -> None:
        self._previous: list[tuple[str, Any, str]] = []
        self._serial = 0

    def update(self, sessions: list[tuple[str, Any]]) -> list[tuple[str, Any]]:
        remaining = list(self._previous)
        result, saved = [], []
        for app_id, obj in sessions:
            found = next((item for item in remaining if item[0] == app_id and item[1] == obj), None)
            if found is None and sum(app == app_id for app, _ in sessions) == 1:
                peers = [item for item in remaining if item[0] == app_id]
                found = peers[0] if len(peers) == 1 else None
            if found:
                remaining.remove(found)
                session_id = found[2]
            else:
                self._serial += 1
                session_id = f"{app_id}::{self._serial}"
            saved.append((app_id, obj, session_id))
            result.append((session_id, obj))
        self._previous = saved
        return result


def choose_session(items: list[dict[str, Any]], selected: str, current: str,
                   previous: str) -> str:
    if any(item["id"] == selected for item in items):
        return selected
    if not items:
        return ""
    def score(item: dict[str, Any]) -> int:
        return (80 * bool(item.get("realMetadata")) + 200 * bool(item.get("playing"))
                + 10 * (item["id"] == current) + 3 * (item["id"] == previous))
    return max(items, key=score)["id"]
