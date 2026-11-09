"""Cached, asynchronous LRCLIB lyrics; no Spotify cookies or audio uploads."""
from __future__ import annotations

from difflib import SequenceMatcher
import hashlib
import json
import logging
from pathlib import Path
import queue
import re
import threading
import time
import unicodedata
import urllib.parse

from http_client import HttpStatusError, fetch_json

LOG = logging.getLogger('caelestia.lyrics')
TIMESTAMP = re.compile(r'\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]')
DECORATION = re.compile(r'\s*[\[(](?:official\s*)?(?:music\s*)?(?:video|audio|lyric(?:s)?(?:\s+video)?|visuali[sz]er|hd|4k)[\])]\s*', re.I)


def empty_lyrics(state='idle', track_key='', error=''):
    return dict(state=state, trackKey=track_key, lines=[], plainText='', source='LRCLIB', error=error)


def normalized(value):
    value = unicodedata.normalize('NFKC', str(value or '')).casefold()
    return ' '.join(re.sub(r'[^\w]+', ' ', value, flags=re.UNICODE).split())


def parse_lrc(text):
    """Preserve line timestamps, repeated timestamps and millisecond offsets."""
    text = str(text or '')[:100000]
    offset_match = re.search(r'\[offset:\s*([+-]?\d+)\]', text, flags=re.I)
    offset = int(offset_match.group(1)) / 1000 if offset_match else 0
    lines = []
    for raw in text.splitlines():
        stamps = list(TIMESTAMP.finditer(raw))
        content = TIMESTAMP.sub('', raw).strip()
        if not stamps or not content:
            continue
        for stamp in stamps:
            minutes, seconds, fraction = stamp.groups()
            if int(seconds) >= 60:
                continue
            value = int(minutes)*60 + int(seconds) + (int(fraction)/10**len(fraction) if fraction else 0) + offset
            lines.append({'time': max(0.0, value), 'text': content[:1000]})
    lines.sort(key=lambda item: item['time'])
    return lines[:1600]


def query_track(media):
    title = DECORATION.sub(' ', str(media.get('title') or '')).strip()
    artist = str(media.get('artist') or '').strip()
    # Common YouTube music titles carry the actual artist before the dash.
    if ' - ' in title and (not artist or artist.casefold().endswith(('vevo', 'topic'))):
        artist, title = title.split(' - ', 1)
    return {'title': title, 'artist': artist, 'album': str(media.get('album') or '').strip(),
            'duration': max(0, float(media.get('duration') or 0))}


def track_key(media):
    return str(media.get('trackId') or hashlib.sha256('|'.join(str(media.get(key) or '') for key in ('sessionId', 'title', 'artist', 'album')).encode()).hexdigest())


def candidate_score(candidate, track):
    if not isinstance(candidate, dict):
        return -1
    title_a, title_b = normalized(candidate.get('trackName')), normalized(track['title'])
    if not title_a or not title_b or SequenceMatcher(None, title_a, title_b).ratio() < 0.94:
        return -1
    artist_a, artist_b = normalized(candidate.get('artistName')), normalized(track['artist'])
    tokens_a, tokens_b = set(artist_a.split()), set(artist_b.split())
    if not tokens_a or not tokens_b:
        return -1
    overlap = len(tokens_a & tokens_b)/min(len(tokens_a), len(tokens_b))
    if artist_a != artist_b and overlap < 0.8:
        return -1
    duration = float(candidate.get('duration') or 0)
    difference = abs(duration-track['duration']) if track['duration'] else 0
    if track['duration'] and (not duration or difference > max(3, track['duration']*0.02)):
        return -1
    album_bonus = normalized(candidate.get('albumName')) == normalized(track['album']) and bool(track['album'])
    return 10 + 2*overlap + int(album_bonus) - difference/10


class LyricsWorker:
    def __init__(self, publish, cache_dir, *, fetch=fetch_json, autostart=True,
                 retry_delays=(1.0, 3.0)):
        self._publish_callback = publish
        self._fetch = fetch
        self._cache_path = Path(cache_dir)/'lyrics-cache-v1.json'
        self._queue = queue.Queue(maxsize=1)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._retry_wake = threading.Event()
        self._retry_delays = tuple(max(0.0, float(delay)) for delay in retry_delays[:2])
        self._generation = 0
        self._current_key = ''
        self._request_id = None
        self._cache = {}
        try:
            if self._cache_path.stat().st_size < 4*1024*1024:
                self._cache = json.loads(self._cache_path.read_text('utf-8')).get('items', {})
        except (OSError, ValueError, AttributeError):
            pass
        self._thread = threading.Thread(target=self._run, name='caelestia-lyrics', daemon=True)
        if autostart:
            self._thread.start()

    @property
    def current_key(self):
        with self._lock:
            return self._current_key

    def request(self, media, *, force=False):
        key = track_key(media) if media.get('available') else ''
        if media.get('metadataPending') and key == self.current_key:
            return
        track = query_track(media)
        request_id = (key, normalized(track['title']), normalized(track['artist']), normalized(track['album']), round(track['duration']))
        with self._lock:
            if request_id == self._request_id and not force:
                return
            self._request_id = request_id
            self._current_key = key
            self._generation += 1
            generation = self._generation
        self._retry_wake.set()
        if not key or not track['title'] or not track['artist'] or normalized(track['title']) in {'unknown title', 'nothing playing', 'a site is playing media', 'google chrome'}:
            self._publish(generation, empty_lyrics('idle', key))
            return
        self._publish(generation, empty_lyrics('loading', key))
        item = (generation, key, track, force)
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            self._queue.put_nowait(item)

    def _publish(self, generation, result):
        with self._lock:
            current = generation == self._generation
        if current and not self._stop.is_set():
            self._publish_callback(result)

    def _is_current(self, generation):
        with self._lock:
            return generation == self._generation and not self._stop.is_set()

    def _wait_retry(self, generation, delay):
        deadline = time.monotonic() + delay
        while True:
            # Clear first, then check the generation. A new request arriving
            # between that check and wait() wakes this worker immediately.
            self._retry_wake.clear()
            if not self._is_current(generation):
                return False
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return True
            self._retry_wake.wait(remaining)

    def _load_with_retries(self, generation, track, *, force=False):
        for attempt in range(len(self._retry_delays) + 1):
            if not self._is_current(generation):
                return None
            if attempt and not self._wait_retry(generation, self._retry_delays[attempt - 1]):
                return None
            try:
                return self._load_track(track, force=force)
            except OSError as error:
                retryable = (not isinstance(error, HttpStatusError)
                             or error.status == 429 or 500 <= error.status <= 599)
                if not retryable or attempt == len(self._retry_delays):
                    raise
                LOG.debug('Lyrics service temporarily unavailable; retrying attempt %d', attempt + 2)
        return None

    def _load_track(self, track, *, force=False):
        identity = hashlib.sha256(json.dumps(track, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        cached = self._cache.get(identity, {})
        lifetime = 6*3600 if cached.get('data', {}).get('state') == 'not_found' else 30*86400
        if not force and time.time()-cached.get('saved', 0) < lifetime:
            return dict(cached['data'])
        candidate = None
        base = {'track_name': track['title'], 'artist_name': track['artist']}
        if track['duration']:
            exact = {**base, 'duration': round(track['duration'], 2)}
            if track['album']:
                exact['album_name'] = track['album']
            try:
                item = self._fetch('https://lrclib.net/api/get?'+urllib.parse.urlencode(exact))
                if candidate_score(item, track) >= 0:
                    candidate = item
            except HttpStatusError as error:
                if error.status != 404:
                    raise
        if candidate is None:
            primary_artist = re.split(r',|;| & | feat\.? | ft\.? ', track['artist'], flags=re.I)[0].strip()
            searches = [base]
            if primary_artist and primary_artist != track['artist']:
                searches.append({**base, 'artist_name': primary_artist})
            for search in searches:
                items = self._fetch('https://lrclib.net/api/search?'+urllib.parse.urlencode(search))
                scored = [(candidate_score(item, track), item) for item in items[:100]] if isinstance(items, list) else []
                scored.sort(key=lambda item: item[0], reverse=True)
                if scored and scored[0][0] >= 0:
                    candidate = scored[0][1]
                    break
        result = empty_lyrics('not_found')
        if candidate:
            lines = parse_lrc(candidate.get('syncedLyrics'))
            plain = str(candidate.get('plainLyrics') or '')[:64000].strip()
            if candidate.get('instrumental'):
                result = empty_lyrics('instrumental')
            elif lines:
                result.update(state='synced', lines=lines)
            elif plain:
                result.update(state='plain', plainText=plain)
        self._cache[identity] = {'saved': time.time(), 'data': result}
        self._cache = dict(sorted(self._cache.items(), key=lambda item: item[1].get('saved', 0))[-64:])
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            raw = json.dumps({'version': 1, 'items': self._cache}, ensure_ascii=False)
            if len(raw.encode('utf-8')) <= 4*1024*1024:
                temporary = self._cache_path.with_suffix('.tmp')
                temporary.write_text(raw, encoding='utf-8')
                temporary.replace(self._cache_path)
        except OSError:
            LOG.debug('Lyrics cache could not be saved', exc_info=True)
        return result

    def _run(self):
        while not self._stop.is_set():
            try:
                generation, key, track, force = self._queue.get(timeout=0.3)
            except queue.Empty:
                continue
            with self._lock:
                current = generation == self._generation
            if not current:
                continue
            try:
                result = self._load_with_retries(generation, track, force=force)
            except (OSError, ValueError, TypeError, KeyError) as error:
                LOG.debug('Lyrics lookup failed: %s', error)
                result = empty_lyrics('error', error='Lyrics service unavailable')
            if result is None:
                continue  # Superseded/stopped while waiting; publish no old state.
            result['trackKey'] = key
            self._publish(generation, result)

    def stop(self):
        self._stop.set()
        self._retry_wake.set()
        if self._thread.is_alive():
            self._thread.join(timeout=0.6)
