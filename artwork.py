"""Strictly matched, cached music artwork from MusicBrainz/Cover Art Archive.

Only music with exposed title, artist and duration is queried. Native artwork
remains the fallback. No album image is bundled or inferred for arbitrary video.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import math
from pathlib import Path
import queue
import re
import threading
import time
import urllib.parse
import uuid

from PIL import Image

from http_client import HttpStatusError, fetch_bytes, fetch_json
from lyrics import candidate_score, normalized, query_track

LOG = logging.getLogger('caelestia.artwork')
MAX_IMAGE_BYTES = 3 * 1024 * 1024


def contact_user_agent(cache_dir, contact_email=None):
    if contact_email is None:
        try:
            path = Path(cache_dir) / 'artwork-contact.json'
            if path.stat().st_size <= 4096:
                contact_email = json.loads(path.read_text('utf-8')).get('contactEmail', '')
        except (OSError, ValueError, AttributeError):
            contact_email = ''
    email = str(contact_email or '').strip()
    if (len(email) > 254 or not email.isascii()
            or re.fullmatch(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+', email) is None):
        return ''
    return 'CaelestiaWindows/1.0 (' + email + ')'


def music_query(media):
    if not media.get('available') or not media.get('trackId') or media.get('metadataPending'):
        return None
    track = query_track(media)
    if (not track['title'] or not track['artist'] or not math.isfinite(track['duration'])
            or not 10 <= track['duration'] <= 3600
            or max(len(track['title']), len(track['artist']), len(track['album'])) > 512):
        return None
    if normalized(track['title']) in {'unknown title', 'nothing playing', 'google chrome',
                                      'a site is playing media', 'waiting for track information'}:
        return None
    if normalized(track['artist']) in {'youtube', 'youtube music', 'google chrome', 'spotify', 'media player'}:
        return None
    # A native square cover already at this size needs no external lookup.
    if min(int(media.get('artworkWidth') or 0), int(media.get('artworkHeight') or 0)) >= 512:
        return None
    return track


def release_id(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return ''


def source_url(url):
    parsed = urllib.parse.urlsplit(str(url or ''))
    if (parsed.scheme != 'https' or parsed.hostname != 'musicbrainz.org'
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        return ''
    match = re.fullmatch(r'/release/([a-fA-F0-9-]+)', parsed.path)
    identifier = release_id(match[1]) if match else ''
    return 'https://musicbrainz.org/release/' + identifier if identifier else ''


def artist_credit(item):
    credits = item.get('artist-credit', [])
    if not isinstance(credits, list):
        return ''
    return ''.join(str(part.get('name') or part.get('artist', {}).get('name') or '')
                   + str(part.get('joinphrase') or '')
                   for part in credits if isinstance(part, dict)).strip()


def matching_candidate(item, track):
    if not isinstance(item, dict) or item.get('video'):
        return False
    try:
        converted = dict(trackName=item.get('title'), artistName=artist_credit(item),
                         albumName=track['album'], duration=float(item.get('length') or 0)/1000)
        if candidate_score(converted, track) < 0:
            return False
        # Cover art must match this recording, rather than a similar search hit.
        if normalized(converted['trackName']) != normalized(track['title']):
            return False
        if normalized(converted['artistName']) != normalized(track['artist']):
            return False
        tolerance = max(3, min(5, track['duration'] * .02))
        return abs(converted['duration'] - track['duration']) <= tolerance
    except (ValueError, TypeError, OverflowError):
        return False


def candidate_releases(item, track):
    releases = item.get('releases', [])
    if not isinstance(releases, list):
        return []
    choices = []
    for release in releases:
        if not isinstance(release, dict):
            continue
        identifier = release_id(release.get('id'))
        if not identifier or (track['album'] and normalized(release.get('title')) != normalized(track['album'])):
            continue
        group = release.get('release-group', {})
        group = group if isinstance(group, dict) else {}
        compilation = 'Compilation' in group.get('secondary-types', [])
        official = release.get('status', 'Official') == 'Official'
        album = group.get('primary-type') == 'Album'
        choices.append(((not official, compilation, not album, release.get('date', '9999')), identifier))
    choices.sort()
    return list(dict.fromkeys(identifier for _, identifier in choices))


def _search_phrase(value):
    return '"' + re.sub(r'([+\-!(){}\[\]^"~*?:\\/]|&&|\|\|)', r'\\\1', value) + '"'


def decode_artwork(contents):
    if not isinstance(contents, bytes) or not 0 < len(contents) <= MAX_IMAGE_BYTES:
        return None
    try:
        with Image.open(io.BytesIO(contents)) as image:
            width, height = image.size
            if min(width, height) < 300 or width * height > 9_000_000:
                return None
            extension = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}.get(image.format)
            if extension is None:
                return None
            image.load()  # Validate the entire image, including truncated data.
        return extension, width, height
    except (OSError, ValueError, Image.DecompressionBombError):
        return None


def merge_artwork(media, override):
    """Never apply another track's result or downgrade a better native image."""
    if not override or not media.get('trackId') or override.get('trackId') != media.get('trackId'):
        return dict(media)
    width, height = int(override.get('artworkWidth') or 0), int(override.get('artworkHeight') or 0)
    native_width, native_height = int(media.get('artworkWidth') or 0), int(media.get('artworkHeight') or 0)
    if (width * height <= native_width * native_height
            or min(width, height) <= min(native_width, native_height)):
        return dict(media)
    return {**media, **{key: override[key] for key in (
        'artwork', 'artworkWidth', 'artworkHeight', 'artworkSource', 'artworkSourceUrl')}}


class ArtworkWorker:
    def __init__(self, publish, cache_dir, *, fetch=fetch_json, download=fetch_bytes,
                 autostart=True, min_interval=3.1, contact_email=None):
        self._publish_callback = publish
        self._fetch, self._download = fetch, download
        self._cache_dir = Path(cache_dir)
        self._cache_path = self._cache_dir / 'artwork-cache-v1.json'
        self._user_agent = contact_user_agent(cache_dir, contact_email)
        self._cache = {}
        try:
            if self._cache_path.stat().st_size < 1024 * 1024:
                saved = json.loads(self._cache_path.read_text('utf-8')).get('items', {})
                if isinstance(saved, dict):
                    self._cache = {key: value for key, value in saved.items() if isinstance(value, dict)}
        except (OSError, ValueError, AttributeError):
            pass
        self._queue = queue.Queue(maxsize=1)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._generation, self._current_key = 0, ''
        self._request_id = None
        self._last_query = -float('inf')
        self._last_art_request = -float('inf')
        self._min_interval = max(0.0, float(min_interval))
        self._thread = threading.Thread(target=self._run, name='caelestia-artwork', daemon=True)
        if autostart and self.enabled:
            self._thread.start()

    @property
    def current_key(self):
        with self._lock:
            return self._current_key

    @property
    def enabled(self):
        return bool(self._user_agent)

    def request(self, media, *, force=False):
        key = str(media.get('trackId') or '') if media.get('available') else ''
        if media.get('metadataPending') and key == self.current_key:
            return
        track = music_query(media) if self.enabled else None
        request_id = (key, json.dumps(track, sort_keys=True, ensure_ascii=False))
        with self._lock:
            if request_id == self._request_id and not force:
                return
            self._request_id, self._current_key = request_id, key
            self._generation += 1
            generation = self._generation
        if not key or track is None:
            return
        item = (generation, key, track, force)
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            self._queue.put_nowait(item)

    def _is_current(self, generation):
        with self._lock:
            return generation == self._generation and not self._stop.is_set()

    def _publish(self, generation, result):
        if self._is_current(generation) and result is not None:
            self._publish_callback(result)

    def _load_track(self, track, *, force=False, still_current=lambda: True):
        if not self.enabled:
            return None
        identity = hashlib.sha256(json.dumps(track, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        cached = self._cache.get(identity, {})
        data = cached.get('data') if isinstance(cached, dict) else None
        lifetime = 6 * 3600 if not data else 30 * 86400
        if not force and time.time() - cached.get('saved', 0) < lifetime:
            if not data:
                return None
            name = data.get('file', '')
            if isinstance(name, str) and re.fullmatch(r'art-hq-[a-f0-9]{64}\.(jpg|png|webp)', name):
                path = self._cache_dir / name
                if path.is_file() and source_url(data.get('artworkSourceUrl')):
                    return {**data, 'artwork': path.as_uri()}
        delay = self._min_interval - (time.monotonic() - self._last_query)
        if delay > 0 and self._stop.wait(delay):
            return None
        if not still_current() or self._stop.is_set():
            return None
        self._last_query = time.monotonic()
        tolerance = max(3, min(5, track['duration'] * .02))
        duration_min = max(0, int((track['duration'] - tolerance) * 1000))
        duration_max = int((track['duration'] + tolerance) * 1000)
        expression = ('recording:' + _search_phrase(track['title']) + ' AND artist:'
                      + _search_phrase(track['artist']) + f' AND dur:[{duration_min} TO {duration_max}] AND video:false')
        query = urllib.parse.urlencode({'query': expression, 'fmt': 'json', 'limit': 8})
        response = self._fetch('https://musicbrainz.org/ws/2/recording/?' + query,
                               user_agent=self._user_agent)
        results = response.get('recordings', []) if isinstance(response, dict) else []
        releases = []
        for candidate in results[:8] if isinstance(results, list) else []:
            if matching_candidate(candidate, track):
                releases.extend(candidate_releases(candidate, track))
        result = None
        for identifier in list(dict.fromkeys(releases))[:3]:
            if not still_current() or self._stop.is_set():
                return None
            delay = 1.1 - (time.monotonic() - self._last_art_request)
            if delay > 0 and self._stop.wait(delay):
                return None
            if not still_current():
                return None
            self._last_art_request = time.monotonic()
            try:
                contents = self._download('https://coverartarchive.org/release/' + identifier + '/front-500',
                                          max_bytes=MAX_IMAGE_BYTES, accept='image/*',
                                          user_agent=self._user_agent)
            except HttpStatusError as error:
                if error.status == 404:
                    continue
                raise
            decoded = decode_artwork(contents)
            if decoded:
                extension, width, height = decoded
                filename = 'art-hq-' + hashlib.sha256(contents).hexdigest() + '.' + extension
                self._cache_dir.mkdir(parents=True, exist_ok=True)
                path = self._cache_dir / filename
                if not path.exists():
                    path.write_bytes(contents)
                result = dict(artwork=path.as_uri(), file=filename,
                              artworkWidth=width, artworkHeight=height,
                              artworkSource='Cover Art Archive',
                              artworkSourceUrl='https://musicbrainz.org/release/' + identifier)
                break
        self._cache[identity] = {'saved': time.time(), 'data': result}
        self._save_cache()
        return result

    def _save_cache(self):
        self._cache = dict(sorted(self._cache.items(), key=lambda item: item[1].get('saved', 0))[-128:])
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            temporary = self._cache_path.with_suffix('.tmp')
            temporary.write_text(json.dumps({'version': 1, 'items': self._cache}, ensure_ascii=False), encoding='utf-8')
            temporary.replace(self._cache_path)
        except OSError:
            LOG.debug('Artwork cache could not be saved', exc_info=True)

    def _run(self):
        while not self._stop.is_set():
            try:
                generation, key, track, force = self._queue.get(timeout=.3)
            except queue.Empty:
                continue
            if not self._is_current(generation):
                continue
            try:
                result = self._load_track(track, force=force,
                                          still_current=lambda: self._is_current(generation))
            except (OSError, ValueError, TypeError, KeyError) as error:
                LOG.debug('Artwork lookup failed: %s', error)
                result = None
            if result is not None:
                self._publish(generation, {**result, 'trackId': key})

    def stop(self):
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=.6)
