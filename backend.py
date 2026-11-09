"""Windows services for the Caelestia dashboard.

The UI only receives immutable snapshots, through queued Qt signals. Network,
WinRT media calls and audio acquisition never run on Qt's GUI/render thread.
Audio buffers are analysed in memory, and are never saved or uploaded.
"""
from __future__ import annotations

import asyncio
import ctypes
import datetime as dt
import hashlib
import io
import json
import logging
import math
import os
from pathlib import Path
import queue
import threading
import time
from typing import Any
import urllib.parse
import urllib.request

import numpy as np
import psutil
from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot

from media_state import (ArtworkTransition, MetadataTransition, StableSessionIds,
                         TimelineAnchor, choose_session, metadata_is_generic)
from lyrics import LyricsWorker, empty_lyrics
from artwork import ArtworkWorker, merge_artwork
from weather_config import load_weather_location

LOG = logging.getLogger("caelestia.backend")
CACHE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CaelestiaWindows" / "cache"
BAND_COUNT = 60  # Caelestia GlobalConfig.services.visualiserBars default.


def _fetch_weather_json(url: str) -> dict[str, Any]:
    """Fetch through Windows' verified TLS transport, independent of OpenSSL.

    The packaged application uses Schannel and Windows' trust store. This avoids
    a frozen Python/OpenSSL provider-path dependency and uses the user's normal
    Windows proxy configuration. No certificate checks are disabled.
    """
    if os.name != 'nt':
        with urllib.request.urlopen(url, timeout=12) as response:
            return json.load(response)
    from ctypes import wintypes as wt
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname:
        raise ValueError('Weather requests require HTTPS')
    api = ctypes.WinDLL('winhttp.dll', use_last_error=True)
    handle = wt.HANDLE
    api.WinHttpOpen.argtypes = [wt.LPCWSTR, wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD]
    api.WinHttpOpen.restype = handle
    api.WinHttpConnect.argtypes = [handle, wt.LPCWSTR, wt.WORD, wt.DWORD]
    api.WinHttpConnect.restype = handle
    api.WinHttpOpenRequest.argtypes = [handle, wt.LPCWSTR, wt.LPCWSTR, wt.LPCWSTR,
                                       wt.LPCWSTR, ctypes.c_void_p, wt.DWORD]
    api.WinHttpOpenRequest.restype = handle
    api.WinHttpSetTimeouts.argtypes = [handle, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    api.WinHttpSendRequest.argtypes = [handle, wt.LPCWSTR, wt.DWORD, ctypes.c_void_p,
                                     wt.DWORD, wt.DWORD, ctypes.c_size_t]
    api.WinHttpReceiveResponse.argtypes = [handle, ctypes.c_void_p]
    api.WinHttpQueryHeaders.argtypes = [handle, wt.DWORD, wt.LPCWSTR, ctypes.c_void_p,
                                       ctypes.POINTER(wt.DWORD), ctypes.POINTER(wt.DWORD)]
    api.WinHttpQueryDataAvailable.argtypes = [handle, ctypes.POINTER(wt.DWORD)]
    api.WinHttpReadData.argtypes = [handle, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD)]
    api.WinHttpCloseHandle.argtypes = [handle]
    opened = []
    def require(value):
        if not value:
            code = ctypes.get_last_error()
            raise OSError(code, f'Windows weather connection failed ({code})')
        return value
    try:
        session = require(api.WinHttpOpen('CaelestiaWindows/1.0', 4, None, None, 0))
        opened.append(session)
        require(api.WinHttpSetTimeouts(session, 3000, 5000, 5000, 12000))
        connection = require(api.WinHttpConnect(session, parsed.hostname, parsed.port or 443, 0))
        opened.append(connection)
        resource = parsed.path or '/'
        if parsed.query:
            resource += '?' + parsed.query
        request = require(api.WinHttpOpenRequest(connection, 'GET', resource, None, None, None, 0x00800000))
        opened.append(request)
        require(api.WinHttpSendRequest(request, 'Accept: application/json\r\n', 0xFFFFFFFF, None, 0, 0, 0))
        require(api.WinHttpReceiveResponse(request, None))
        status = wt.DWORD()
        status_length = wt.DWORD(ctypes.sizeof(status))
        require(api.WinHttpQueryHeaders(request, 19 | 0x20000000, None,
                                       ctypes.byref(status), ctypes.byref(status_length), None))
        if status.value != 200:
            raise OSError(f'Weather service returned HTTP {status.value}')
        result = bytearray()
        while True:
            available = wt.DWORD()
            require(api.WinHttpQueryDataAvailable(request, ctypes.byref(available)))
            if available.value == 0:
                break
            size = min(available.value, 65536)
            buffer = ctypes.create_string_buffer(size)
            received = wt.DWORD()
            require(api.WinHttpReadData(request, buffer, size, ctypes.byref(received)))
            if not received.value:
                break
            result.extend(buffer.raw[:received.value])
            if len(result) > 2 * 1024 * 1024:
                raise ValueError('Weather response exceeded expected size')
        return json.loads(result.decode('utf-8'))
    finally:
        for item in reversed(opened):
            api.WinHttpCloseHandle(item)


def _seconds(value: Any) -> float:
    if hasattr(value, "total_seconds"):
        return max(0.0, value.total_seconds())
    try:
        return max(0.0, float(value) / 10_000_000)
    except (ValueError, TypeError):
        return 0.0


def _clock(seconds: float) -> str:
    n = max(0, int(seconds))
    return f"{n // 60}:{n % 60:02d}"


def _weather_kind(code: int, daylight: bool = True) -> tuple[str, str]:
    if code == 0:
        return ("Clear sky", "clear_day" if daylight else "clear_night")
    if code in (1, 2):
        return ("Partly cloudy", "partly_cloudy_day" if daylight else "partly_cloudy_night")
    if code == 3:
        return ("Overcast", "cloud")
    if code in (45, 48):
        return ("Fog", "foggy")
    if code in (51, 53, 55, 56, 57):
        return ("Drizzle", "rainy_light")
    if code in (61, 63, 65, 66, 67, 80, 81, 82):
        return ("Rain", "rainy")
    if code in (71, 73, 75, 77, 85, 86):
        return ("Snow", "weather_snowy")
    if code in (95, 96, 99):
        return ("Thunderstorm", "thunderstorm")
    return ("Cloudy", "cloud")


def _app_name(app_id: str) -> str:
    app_lower = app_id.lower()
    for fragment, label in (("spotify", "Spotify"), ("chrome", "Google Chrome"),
                            ("msedge", "Microsoft Edge"), ("vlc", "VLC media player"),
                            ("firefox", "Firefox"), ("zunemusic", "Media Player"),
                            ("music.ui", "Media Player"), ("applemusic", "Apple Music"),
                            ("brave", "Brave"), ("opera", "Opera"),
                            ("foobar", "foobar2000"), ("screensketch", "Snipping Tool")):
        if fragment in app_lower:
            return label
    name = app_id.rsplit("!", 1)[-1].rsplit("\\", 1)[-1]
    return name.removesuffix(".exe") or "Media player"


def _empty_media() -> dict[str, Any]:
    return dict(available=False, title="Nothing playing", artist="", album="",
                artwork="", playing=False, position=0.0, duration=0.0,
                positionLabel="0:00", durationLabel="0:00", sessions=[],
                sessionId="", appName="Choose a player", canPlayPause=False,
                canNext=False, canPrevious=False, canSeek=False, canShuffle=False,
                shuffle=False, canRepeat=False, repeat=0, error="", trackId="",
                sourceAppId="", trackNumber=0, albumTrackCount=0,
                artworkWidth=0, artworkHeight=0, metadataPending=False,
                playbackRate=1.0, artworkSource="", artworkSourceUrl="")


class _MediaSession:
    def __init__(self, session_id: str, session: Any):
        self.id, self.session = session_id, session
        self.app_id = session.source_app_user_model_id
        self.app_name = _app_name(self.app_id)
        self.metadata = MetadataTransition(session_id, self.app_name)
        self.artwork = ArtworkTransition()
        self.clock = TimelineAnchor()
        self.tokens: list[tuple[str, Any]] = []
        self.task: asyncio.Task | None = None
        self.revision = 0
        self.metadata_dirty = self.native_dirty = True
        self.next_metadata = self.next_artwork = self.next_native = 0.0
        self.artwork_attempts = 0
        self.playing = False
        self.rate = 1.0
        self.duration = self.position = self.start = 0.0
        self.updated: Any = None
        self.controls: dict[str, Any] = {}


async def _read_media_thumbnail(thumbnail: Any) -> tuple[bytes, str, int, int] | None:
    """Read and validate the provider's original image, without re-encoding it."""
    from PIL import Image
    from winrt.windows.storage.streams import DataReader
    stream = reader = None
    try:
        stream = await thumbnail.open_read_async()
        size = int(stream.size)
        if not 0 < size <= 8 * 1024 * 1024:
            return None
        reader = DataReader(stream)
        contents = bytearray()
        while len(contents) < size:
            loaded = int(await reader.load_async(min(65536, size - len(contents))))
            if not loaded:
                break
            block = bytearray(loaded)
            reader.read_bytes(block)
            contents.extend(block)
        if len(contents) != size:
            return None
        native = bytes(contents)
        with Image.open(io.BytesIO(native)) as image:
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > 36_000_000:
                return None
            kind = (image.format or "").lower()
            image.verify()
        # Only formats supported by the bundled Qt image plugins.
        extension = {"jpeg": "jpg", "png": "png", "webp": "webp", "bmp": "bmp",
                     "gif": "gif", "ico": "ico"}.get(kind)
        return (native, extension, width, height) if extension else None
    finally:
        for resource in (reader, stream):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    pass


class Backend(QObject):
    dataChanged = Signal()
    audioChanged = Signal()
    _partUpdated = Signal(str, object)

    def __init__(self, parent: QObject | None = None, *, start_workers: bool = True):
        super().__init__(parent)
        CACHE.mkdir(parents=True, exist_ok=True)
        self._weather_location = load_weather_location()
        self._stop_event = threading.Event()
        self._refresh_weather = threading.Event()
        self._visualiser_active = threading.Event()
        self._visualiser_active.set()
        self._audio_lock = threading.Lock()
        self._audio_latest = np.zeros(BAND_COUNT, dtype=np.float32)
        self._audio_last_frame = time.monotonic()
        self._audio_levels = [0.0] * BAND_COUNT
        self._audio_peak = 0.0
        self._selected_session = ""
        self._selected_drive = os.environ.get("SystemDrive", "C:") + "\\"
        self._media_commands: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._threads: list[threading.Thread] = []
        self._audio_stream: Any = None
        self._media_loop: asyncio.AbstractEventLoop | None = None
        self._media_wake: asyncio.Event | None = None
        self._lyrics_worker: LyricsWorker | None = None
        self._artwork_worker: ArtworkWorker | None = None
        self._artwork_override: dict[str, Any] = {}
        self._data = {
            "system": {
                "cpuPercent": 0.0, "cpuName": "Processor", "memoryPercent": 0.0,
                "memoryUsed": 0, "memoryTotal": 0, "drives": [],
                "selectedDrive": self._selected_drive, "storagePercent": 0.0,
                "storageUsed": 0, "storageTotal": 0, "downloadRate": 0.0,
                "uploadRate": 0.0, "downloadTotal": 0, "uploadTotal": 0,
                "networkHistory": [0.0] * 48, "batteryPercent": 0.0,
                "batteryCharging": False, "batteryAvailable": False,
                "uptime": 0, "temperature": -1.0, "temperatureAvailable": False,
            },
            "media": _empty_media(),
            "lyrics": empty_lyrics(),
            "weather": {
                "available": False, "city": self._weather_location.city, "country": self._weather_location.country,
                "temperature": 0.0, "feelsLike": 0.0, "humidity": 0,
                "windSpeed": 0.0, "condition": "Loading weather", "icon": "cloud",
                "sunrise": "—", "sunset": "—", "days": [],
                "error": "", "stale": False, "source": "Open-Meteo",
            },
            "audio": {"available": False, "device": "", "error": ""},
        }
        self._partUpdated.connect(self._apply_part)
        self._audio_timer = QTimer(self)
        self._audio_timer.setInterval(25)
        self._audio_timer.timeout.connect(self._publish_audio)
        self._audio_timer.start()
        if start_workers:
            self._lyrics_worker = LyricsWorker(lambda value:self._partUpdated.emit('lyrics',value), CACHE)
            self._artwork_worker = ArtworkWorker(lambda value:self._partUpdated.emit('HQcover',value), CACHE)
            for name, target in (("system", self._system_worker),
                                 ("weather", self._weather_worker),
                                 ("media", self._media_worker),
                                 ("audio", self._audio_worker)):
                thread = threading.Thread(target=target, name=f"caelestia-{name}", daemon=True)
                self._threads.append(thread)
                thread.start()

    @Property("QVariantMap", notify=dataChanged)
    def data(self) -> dict[str, Any]:
        return self._data

    @Property("QVariantList", notify=audioChanged)
    def audioLevels(self) -> list[float]:
        return self._audio_levels

    @Property(float, notify=audioChanged)
    def audioPeak(self) -> float:
        return self._audio_peak

    @Slot(str, object)
    def _apply_part(self, key: str, value: Any) -> None:
        if self._stop_event.is_set():
            return
        if key == 'lyrics' and self._lyrics_worker is not None and value.get('trackKey') != self._lyrics_worker.current_key:
            return
        if key == 'HQcover':
            current = self._data['media']
            if (self._artwork_worker is None or value.get('trackId') != current.get('trackId')
                    or value.get('trackId') != self._artwork_worker.current_key):
                return
            self._artwork_override = value
            enriched = merge_artwork(current, value)
            if enriched != current:
                self._data = {**self._data, 'media': enriched}
                self.dataChanged.emit()
            return
        native_media = value if key == 'media' else None
        if key == 'media':
            if value.get('trackId') != self._data['media'].get('trackId'):
                self._artwork_override = {}
            value = merge_artwork(value, self._artwork_override)
        self._data = {**self._data, key: value}
        self.dataChanged.emit()
        if key == 'media' and self._lyrics_worker is not None:
            self._lyrics_worker.request(value)
        if native_media is not None and self._artwork_worker is not None:
            self._artwork_worker.request(native_media)

    @Slot()
    def _publish_audio(self) -> None:
        with self._audio_lock:
            # Some loopback drivers stop delivering buffers when playback stops.
            # Decay on the GUI timer too, so the last spectrum never freezes.
            if time.monotonic() - self._audio_last_frame > 0.15:
                self._audio_latest *= 0.80
            values = self._audio_latest.copy()
        self._audio_levels = values.tolist()
        self._audio_peak = float(np.mean(values))
        self.audioChanged.emit()

    @Slot()
    def refresh(self) -> None:
        self._refresh_weather.set()
        self._queue_media_command('refresh',None)
        if self._lyrics_worker is not None:
            self._lyrics_worker.request(self._data['media'],force=True)
        if self._artwork_worker is not None:
            self._artwork_worker.request(self._data['media'],force=True)

    @Slot(bool)
    def setVisualiserActive(self, enabled: bool) -> None:
        if enabled:
            self._visualiser_active.set()
            self._audio_timer.start()
        else:
            self._visualiser_active.clear()
            self._audio_timer.stop()
            with self._audio_lock:
                self._audio_latest[:] = 0
            self._audio_levels = [0.0] * BAND_COUNT
            self._audio_peak = 0.0
            self.audioChanged.emit()

    @Slot()
    def playPause(self) -> None:
        self._queue_media_command("toggle", None)

    @Slot()
    def nextTrack(self) -> None:
        self._queue_media_command("next", None)

    @Slot()
    def previousTrack(self) -> None:
        self._queue_media_command("previous", None)

    @Slot(float)
    def seek(self, seconds: float) -> None:
        self._queue_media_command("seek", max(0.0, seconds))

    @Slot(str)
    def selectSession(self, session_id: str) -> None:
        self._selected_session = session_id
        self._wake_media()

    def _wake_media(self) -> None:
        loop, wake = self._media_loop, self._media_wake
        if loop is not None and wake is not None:
            try:
                loop.call_soon_threadsafe(wake.set)
            except RuntimeError:
                pass  # The worker's loop has already shut down.

    def _queue_media_command(self, command: str, parameter: Any) -> None:
        self._media_commands.put((command, parameter))
        self._wake_media()

    @Slot(str)
    def selectDrive(self, drive_id: str) -> None:
        known = {item["id"] for item in self._data["system"].get("drives", [])}
        if drive_id in known:
            self._selected_drive = drive_id

    @Slot()
    def toggleShuffle(self) -> None:
        self._queue_media_command("shuffle", not self._data["media"].get("shuffle", False))

    @Slot()
    def cycleRepeat(self) -> None:
        self._queue_media_command("repeat", (self._data["media"].get("repeat", 0) + 1) % 3)

    @Slot()
    def stop(self) -> None:
        self._stop_event.set()
        self._wake_media()
        self._refresh_weather.set()
        self._audio_timer.stop()
        if self._lyrics_worker is not None:
            self._lyrics_worker.stop()
        if self._artwork_worker is not None:
            self._artwork_worker.stop()
        # Audio runs in a callback, so stopping does not depend on playback
        # becoming active. Daemon networking workers have bounded timeouts.
        for thread in self._threads:
            thread.join(timeout=0.6)

    @staticmethod
    def _cpu_name() -> str:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
        except (OSError, ImportError):
            import platform
            return platform.processor() or "Processor"

    @staticmethod
    def _drive_label(path: str) -> str:
        try:
            label = ctypes.create_unicode_buffer(261)
            ok = ctypes.windll.kernel32.GetVolumeInformationW(
                path, label, len(label), None, None, None, None, 0)
            if ok:
                return label.value
        except (AttributeError, OSError):
            pass
        return ""

    def _system_worker(self) -> None:
        cpu_name = self._cpu_name()
        previous = psutil.net_io_counters()
        previous_time = time.monotonic()
        history = [0.0] * 48
        drives: list[dict[str, Any]] = []
        last_disk_scan = 0.0
        psutil.cpu_percent(None)
        while not self._stop_event.is_set():
            try:
                now = time.monotonic()
                elapsed = max(0.1, now - previous_time)
                counters = psutil.net_io_counters()
                down = max(0.0, (counters.bytes_recv - previous.bytes_recv) / elapsed)
                up = max(0.0, (counters.bytes_sent - previous.bytes_sent) / elapsed)
                previous, previous_time = counters, now
                history = history[1:] + [down + up]
                memory = psutil.virtual_memory()
                battery = psutil.sensors_battery()
                if now - last_disk_scan > 15 or not drives:
                    drives = []
                    for disk in psutil.disk_partitions(all=False):
                        if not disk.fstype or "cdrom" in disk.opts:
                            continue
                        try:
                            usage = psutil.disk_usage(disk.mountpoint)
                            drives.append({"id": disk.mountpoint,
                                           "name": disk.device.rstrip("\\/"),
                                           "label": self._drive_label(disk.mountpoint),
                                           "used": usage.used, "total": usage.total,
                                           "free": usage.free, "percent": usage.percent})
                        except (OSError, PermissionError):
                            continue
                    last_disk_scan = now
                chosen = next((d for d in drives if d["id"] == self._selected_drive),
                              drives[0] if drives else {})
                temperature = -1.0
                if hasattr(psutil, "sensors_temperatures"):
                    try:
                        sensors = psutil.sensors_temperatures()
                        readings = [r.current for group in sensors.values() for r in group
                                    if r.current is not None and 0 < r.current < 130]
                        if readings:
                            temperature = max(readings)
                    except (OSError, AttributeError):
                        pass
                value = {
                    "cpuPercent": psutil.cpu_percent(None), "cpuName": cpu_name,
                    "memoryPercent": memory.percent, "memoryUsed": memory.used,
                    "memoryTotal": memory.total, "drives": drives,
                    "selectedDrive": chosen.get("id", self._selected_drive),
                    "storagePercent": chosen.get("percent", 0.0),
                    "storageUsed": chosen.get("used", 0),
                    "storageTotal": chosen.get("total", 0),
                    "downloadRate": down, "uploadRate": up,
                    "downloadTotal": counters.bytes_recv, "uploadTotal": counters.bytes_sent,
                    "networkHistory": history, "batteryAvailable": battery is not None,
                    "batteryPercent": float(battery.percent) if battery else 0.0,
                    "batteryCharging": bool(battery.power_plugged) if battery else False,
                    "uptime": max(0, int(time.time() - psutil.boot_time())),
                    "temperature": temperature, "temperatureAvailable": temperature >= 0,
                }
                self._partUpdated.emit("system", value)
            except Exception as error:
                LOG.warning("System statistics update failed: %s", error)
            self._stop_event.wait(1.0)

    def _weather_worker(self) -> None:
        location = self._weather_location
        cache_path = CACHE / location.cache_name
        cached: dict[str, Any] | None = None
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            cached["stale"] = True
            self._partUpdated.emit("weather", cached)
        except (OSError, ValueError):
            pass
        query = urllib.parse.urlencode({
            "latitude": location.latitude, "longitude": location.longitude,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset",
            "temperature_unit": "celsius", "wind_speed_unit": "kmh",
            "timezone": location.timezone, "forecast_days": 7,
        })
        while not self._stop_event.is_set():
            self._refresh_weather.clear()
            try:
                payload = _fetch_weather_json("https://api.open-meteo.com/v1/forecast?" + query)
                current = payload["current"]
                daily = payload["daily"]
                condition, icon = _weather_kind(int(current["weather_code"]), bool(current["is_day"]))
                days = []
                for index, day in enumerate(daily["time"]):
                    date = dt.date.fromisoformat(day)
                    day_condition, day_icon = _weather_kind(int(daily["weather_code"][index]))
                    days.append({"day": "Today" if index == 0 else date.strftime("%a"),
                                 "date": f"{date.strftime('%b')} {date.day}",
                                 "isoDate": day, "icon": day_icon, "condition": day_condition,
                                 "min": daily["temperature_2m_min"][index],
                                 "max": daily["temperature_2m_max"][index]})
                def solar_time(field: str) -> str:
                    parsed = dt.datetime.fromisoformat(daily[field][0])
                    return parsed.strftime("%I:%M %p").lstrip("0")
                cached = {
                    "available": True, "city": self._weather_location.city, "country": self._weather_location.country,
                    "temperature": current["temperature_2m"],
                    "feelsLike": current["apparent_temperature"],
                    "humidity": current["relative_humidity_2m"],
                    "windSpeed": current["wind_speed_10m"], "condition": condition, "icon": icon,
                    "sunrise": solar_time("sunrise"), "sunset": solar_time("sunset"),
                    "days": days, "error": "", "stale": False,
                    "updated": time.time(), "source": "Open-Meteo",
                }
                self._partUpdated.emit("weather", cached)
                cache_path.write_text(json.dumps(cached, ensure_ascii=False), encoding="utf-8")
                retry_delay = 20 * 60
            except Exception as error:
                LOG.warning("Weather refresh failed: %s", error)
                if cached:
                    cached = {**cached, "stale": True, "error": "Offline · showing saved forecast"}
                    self._partUpdated.emit("weather", cached)
                else:
                    unavailable = {**self._data["weather"], "condition": "Weather unavailable",
                                   "error": "Check your connection", "available": False}
                    self._partUpdated.emit("weather", unavailable)
                retry_delay = 60
            self._refresh_weather.wait(retry_delay)

    def _media_worker(self) -> None:
        try:
            from winrt.runtime import ApartmentType, init_apartment
            init_apartment(ApartmentType.MULTI_THREADED)
            asyncio.run(self._media_main())
        except Exception as error:
            LOG.warning("Windows media sessions unavailable: %s", error)
            value = _empty_media()
            value["error"] = "Windows media sessions unavailable"
            self._partUpdated.emit("media", value)

    async def _media_main(self) -> None:
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as Manager,
            GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
        )
        loop = self._media_loop = asyncio.get_running_loop()
        wake = self._media_wake = asyncio.Event()
        manager = await Manager.request_async()
        identifiers = StableSessionIds()
        records: dict[str, _MediaSession] = {}
        generic_art: dict[str, set[str]] = {}
        manager_tokens: list[tuple[str, Any]] = []
        rescan, next_scan, current_id, chosen_id = True, 0.0, "", ""
        last_value: dict[str, Any] | None = None

        def changed(kind: str, session_id: str = "") -> None:
            nonlocal rescan
            if self._stop_event.is_set():
                return
            if kind in ("sessions_changed", "current_session_changed"):
                rescan = True
            elif session_id in records:
                record = records[session_id]
                record.native_dirty = True
                if kind == "media_properties_changed":
                    record.revision += 1
                    record.metadata_dirty = True
                    record.next_artwork = 0.0
                    record.artwork_attempts = 0
            wake.set()

        def callback(kind: str, session_id: str = ""):
            def receive(_sender: Any, _args: Any) -> None:
                # PyWinRT invokes delegates on a native background thread.
                try:
                    loop.call_soon_threadsafe(changed, kind, session_id)
                except RuntimeError:
                    pass
            return receive

        def subscribe(obj: Any, kind: str, tokens: list, session_id: str = "") -> None:
            try:
                token = getattr(obj, "add_" + kind)(callback(kind, session_id))
                tokens.append((kind, token))
            except (AttributeError, OSError, TypeError) as error:
                LOG.debug("Media event %s unavailable: %s", kind, error)

        def unsubscribe(obj: Any, tokens: list) -> None:
            for kind, token in tokens:
                try:
                    getattr(obj, "remove_" + kind)(token)
                except (AttributeError, OSError, TypeError):
                    pass

        for kind in ("sessions_changed", "current_session_changed"):
            subscribe(manager, kind, manager_tokens)
        try:
            while not self._stop_event.is_set():
                now = time.monotonic()
                try:
                    # Events handle normal updates. A slow discovery fallback
                    # recovers providers that fail to deliver a notification.
                    if rescan or now >= next_scan:
                        pairs = identifiers.update([(s.source_app_user_model_id, s)
                                                    for s in manager.get_sessions()])
                        live = set()
                        for session_id, obj in pairs:
                            live.add(session_id)
                            previous = records.get(session_id)
                            if previous is not None and previous.session == obj:
                                continue
                            if previous is not None:
                                unsubscribe(previous.session, previous.tokens)
                                if previous.task:
                                    previous.task.cancel()
                                # Some providers return fresh COM wrappers on
                                # discovery. A retained stable ID also retains
                                # its clock/cover until genuine metadata changes.
                                record = previous
                                record.session = obj
                                record.tokens = []
                                record.task = None
                                record.revision += 1
                                record.metadata_dirty = record.native_dirty = True
                                record.next_metadata = record.next_artwork = record.next_native = 0.0
                                record.artwork_attempts = 0
                            else:
                                record = records[session_id] = _MediaSession(session_id, obj)
                            for kind in ("media_properties_changed", "playback_info_changed",
                                         "timeline_properties_changed"):
                                subscribe(obj, kind, record.tokens, session_id)
                        for session_id in list(records):
                            if session_id not in live:
                                expired = records.pop(session_id)
                                unsubscribe(expired.session, expired.tokens)
                                if expired.task:
                                    expired.task.cancel()
                        current = manager.get_current_session()
                        current_id = next((key for key, record in records.items()
                                           if record.session == current), "")
                        rescan, next_scan = False, now + 2.0

                    for record in records.values():
                        if record.native_dirty or now >= record.next_native:
                            try:
                                playback = record.session.get_playback_info()
                                timeline = record.session.get_timeline_properties()
                                record.playing = playback.playback_status == PlaybackStatus.PLAYING
                                raw_rate = playback.playback_rate
                                record.rate = float(raw_rate) if raw_rate is not None else 1.0
                                if not math.isfinite(record.rate):
                                    record.rate = 1.0
                                record.start = _seconds(timeline.start_time)
                                record.duration = max(0.0, _seconds(timeline.end_time) - record.start)
                                record.position = max(0.0, _seconds(timeline.position) - record.start)
                                record.updated = timeline.last_updated_time
                                controls = playback.controls
                                record.controls = {
                                    "canPlayPause": bool(controls.is_play_pause_toggle_enabled or controls.is_play_enabled or controls.is_pause_enabled),
                                    "canNext": bool(controls.is_next_enabled),
                                    "canPrevious": bool(controls.is_previous_enabled),
                                    "canSeek": bool(controls.is_playback_position_enabled),
                                    "canShuffle": bool(controls.is_shuffle_enabled),
                                    "shuffle": bool(playback.is_shuffle_active),
                                    "canRepeat": bool(controls.is_repeat_enabled),
                                    "repeat": int(playback.auto_repeat_mode or 0),
                                }
                            except (OSError, AttributeError, TypeError, ValueError) as error:
                                LOG.debug("Media timeline temporarily unavailable: %s", error)
                            record.native_dirty, record.next_native = False, now + 1.0
                        record.clock.observe(track_id=record.metadata.track_id,
                                             position=record.position, duration=record.duration,
                                             playing=record.playing, rate=record.rate,
                                             updated=record.updated, now=now,
                                             wall_now=time.time(), start=record.start)
                        if (record.task is None or record.task.done()) and (
                                record.metadata_dirty or now >= record.next_metadata
                                or now >= record.next_artwork):
                            with_artwork = record.metadata_dirty or now >= record.next_artwork
                            record.metadata_dirty = False
                            record.task = asyncio.create_task(self._refresh_media_properties(
                                record, record.revision, with_artwork, generic_art))

                    items = [{"id": r.id, "name": r.app_name, "playing": r.playing,
                              "title": r.metadata.value.get("title", ""),
                              "realMetadata": bool(r.metadata.track_id and not r.metadata.pending)}
                             for r in records.values()]
                    chosen_id = choose_session(items, self._selected_session, current_id, chosen_id)
                    chosen = records.get(chosen_id)
                    while not self._media_commands.empty():
                        command, parameter = self._media_commands.get_nowait()
                        if chosen is not None:
                            await self._run_media_command(chosen, command, parameter)
                    value = _empty_media()
                    if chosen is not None:
                        position = chosen.clock.position(time.monotonic())
                        value.update(chosen.metadata.value)
                        value.update(chosen.controls)
                        value.update(available=True, sessionId=chosen.id, appName=chosen.app_name,
                                     sourceAppId=chosen.app_id, playing=chosen.playing,
                                     playbackRate=chosen.rate, trackId=chosen.metadata.track_id,
                                     metadataPending=chosen.metadata.pending,
                                     artwork=chosen.artwork.url,
                                     artworkWidth=chosen.artwork.width,
                                     artworkHeight=chosen.artwork.height,
                                     position=position, duration=chosen.clock.duration,
                                     positionLabel=_clock(position),
                                     durationLabel=_clock(chosen.clock.duration))
                    value["sessions"] = items
                    if value != last_value:
                        self._partUpdated.emit("media", value)
                        last_value = value
                except Exception as error:
                    LOG.debug("Windows media session changed during refresh: %s", error)
                try:
                    await asyncio.wait_for(wake.wait(), timeout=0.25)
                except asyncio.TimeoutError:
                    pass
                wake.clear()
        finally:
            unsubscribe(manager, manager_tokens)
            pending = []
            for record in records.values():
                unsubscribe(record.session, record.tokens)
                if record.task is not None:
                    record.task.cancel()
                    pending.append(record.task)
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            self._media_wake = None
            self._media_loop = None

    async def _refresh_media_properties(self, record: _MediaSession, revision: int,
                                        with_artwork: bool,
                                        generic_art: dict[str, set[str]]) -> None:
        """Slow thumbnail/property reads do not stop the shared timeline clock."""
        try:
            props = await asyncio.wait_for(record.session.try_get_media_properties_async(), timeout=3.0)
            if revision != record.revision or self._stop_event.is_set():
                record.metadata_dirty = True
                return
            raw = {"title": props.title, "artist": props.artist, "album": props.album_title,
                   "trackNumber": getattr(props, "track_number", 0),
                   "albumTrackCount": getattr(props, "album_track_count", 0)}
            changed_track = record.metadata.observe(raw, time.monotonic())
            if changed_track:
                record.artwork.set_track(record.metadata.track_id)
                record.artwork_attempts = 0
                record.next_artwork = 0.0
                with_artwork = True
            generic = metadata_is_generic(raw, record.app_name)
            if with_artwork:
                record.artwork_attempts += 1
                # Retry a missing/low-resolution thumbnail after its metadata
                # arrives. Later content revisions get a different URL in QML.
                delays = (0.4, 0.8, 1.5, 3.0, 6.0, 15.0, 30.0)
                record.next_artwork = time.monotonic() + delays[min(record.artwork_attempts - 1, len(delays) - 1)]
                if props.thumbnail is not None:
                    image = await asyncio.wait_for(_read_media_thumbnail(props.thumbnail), timeout=3.0)
                    if image is not None and revision == record.revision and not self._stop_event.is_set():
                        contents, extension, width, height = image
                        digest = hashlib.sha256(contents).hexdigest()
                        logos = generic_art.setdefault(record.app_id, set())
                        # Learn only explicit application placeholders, not an
                        # empty title whose real cover may have arrived first.
                        placeholder_title = str(raw["title"] or "").strip().casefold()
                        if (generic and placeholder_title and placeholder_title not in {
                                "unknown title", "nothing playing", "media player",
                                "waiting for track information"} and len(logos) < 16):
                            logos.add(digest)
                        if not generic and record.metadata.track_id:
                            image_path = CACHE / f"art-{digest}.{extension}"
                            if not image_path.exists():
                                image_path.write_bytes(contents)
                            record.artwork.accept(digest=digest, url=image_path.as_uri(),
                                                  width=width, height=height,
                                                  generic=record.metadata.pending,
                                                  known_logos=logos)
            record.next_metadata = time.monotonic() + (0.4 if record.metadata.pending else 5.0)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            LOG.debug("Media properties or artwork temporarily unavailable: %s", error)
            record.next_metadata = time.monotonic() + 0.8
            record.next_artwork = max(record.next_artwork, time.monotonic() + 0.8)
        finally:
            # Delegate callbacks and this coroutine run on the media loop; no
            # mutable provider state crosses into Qt's GUI thread.
            if self._media_wake is not None:
                self._media_wake.set()

    async def _run_media_command(self, record: _MediaSession, command: str, parameter: Any) -> None:
        try:
            chosen = record.session
            if command == "refresh":
                record.revision += 1
                if record.task is not None and not record.task.done():
                    record.task.cancel()
                record.task = None
                record.metadata_dirty = True
                record.next_metadata = record.next_artwork = 0.0
                record.artwork_attempts = 0
            elif command == "toggle":
                await chosen.try_toggle_play_pause_async()
            elif command == "next":
                await chosen.try_skip_next_async()
                record.metadata_dirty = True
            elif command == "previous":
                await chosen.try_skip_previous_async()
                record.metadata_dirty = True
            elif command == "seek":
                target = max(0.0, float(parameter))
                if record.duration:
                    target = min(target, record.duration)
                accepted = await chosen.try_change_playback_position_async(int((target + record.start) * 10_000_000))
                if accepted:
                    record.clock.seek(target, time.monotonic())
            elif command == "shuffle":
                await chosen.try_change_shuffle_active_async(bool(parameter))
            elif command == "repeat":
                from winrt.windows.media import MediaPlaybackAutoRepeatMode
                await chosen.try_change_auto_repeat_mode_async(MediaPlaybackAutoRepeatMode(int(parameter)))
            record.native_dirty = True
        except Exception as error:
            LOG.debug("Media command %s unsupported: %s", command, error)

    def _audio_worker(self) -> None:
        """Analyse output loopback, with retry on device change/disconnection."""
        try:
            import pyaudiowpatch as pa
        except ImportError as error:
            LOG.warning("Audio visualizer dependency unavailable: %s", error)
            self._partUpdated.emit("audio", {"available": False, "device": "", "error": "Audio visualizer unavailable"})
            return
        while not self._stop_event.is_set():
            manager = None
            stream = None
            try:
                manager = pa.PyAudio()
                device = manager.get_default_wasapi_loopback()
                rate = int(device["defaultSampleRate"])
                channels = max(1, min(2, int(device["maxInputChannels"])))
                window_size = 4096
                window = np.hanning(window_size).astype(np.float32)
                frequencies = np.fft.rfftfreq(window_size, 1.0 / rate)
                edges = np.geomspace(35, min(16000, rate / 2), BAND_COUNT + 1)
                bands = [(max(1, int(np.searchsorted(frequencies, edges[i]))),
                          max(2, int(np.searchsorted(frequencies, edges[i + 1])))) for i in range(BAND_COUNT)]
                ring = np.zeros(window_size, dtype=np.float32)
                smooth = np.zeros(BAND_COUNT, dtype=np.float32)
                last_emit = [0.0]

                def callback(raw: bytes, count: int, info: Any, status: int) -> tuple[None, int]:
                    nonlocal ring, smooth
                    if self._stop_event.is_set():
                        return None, pa.paComplete
                    if not self._visualiser_active.is_set():
                        with self._audio_lock:
                            self._audio_latest *= 0.7
                        return None, pa.paContinue
                    samples = np.frombuffer(raw, dtype=np.float32)
                    if channels > 1:
                        samples = samples[:len(samples) // channels * channels].reshape(-1, channels).mean(axis=1)
                    if len(samples) >= window_size:
                        ring[:] = samples[-window_size:]
                    elif len(samples):
                        ring = np.roll(ring, -len(samples))
                        ring[-len(samples):] = samples
                    now = time.monotonic()
                    if now - last_emit[0] < 1 / 45:
                        return None, pa.paContinue
                    last_emit[0] = now
                    spectrum = np.abs(np.fft.rfft(ring * window)) / (window_size / 2)
                    raw_bands = np.array([np.sqrt(np.mean(spectrum[lo:max(lo + 1, hi)] ** 2))
                                          for lo, hi in bands], dtype=np.float32)
                    # Frequency weighting counteracts natural high-frequency falloff.
                    raw_bands *= np.geomspace(1.0, 3.0, BAND_COUNT).astype(np.float32)
                    db = 20 * np.log10(np.maximum(raw_bands, 1e-8))
                    target = np.clip((db + 68.0) / 56.0, 0.0, 1.0)
                    # Cava-like fast attack, softer decay, with silent output at 0.
                    coefficient = np.where(target > smooth, 0.62, 0.16)
                    smooth += coefficient * (target - smooth)
                    if float(np.max(np.abs(ring))) < 0.00008:
                        smooth *= 0.78
                    with self._audio_lock:
                        self._audio_latest = smooth.copy()
                        self._audio_last_frame = now
                    return None, pa.paContinue

                stream = manager.open(format=pa.paFloat32, channels=channels, rate=rate,
                                      frames_per_buffer=512, input=True,
                                      input_device_index=int(device["index"]),
                                      stream_callback=callback)
                self._audio_stream = stream
                self._partUpdated.emit("audio", {"available": True, "device": device["name"], "error": ""})
                original_name = device["name"]
                checked = time.monotonic()
                while not self._stop_event.wait(0.2):
                    if not stream.is_active():
                        break
                    if time.monotonic() - checked > 5:
                        checked = time.monotonic()
                        current = manager.get_default_wasapi_loopback()
                        if current["name"] != original_name:
                            break
            except Exception as error:
                LOG.warning("Output audio visualizer unavailable; retrying: %s", error)
                self._partUpdated.emit("audio", {"available": False, "device": "", "error": "Waiting for an audio output device"})
            finally:
                self._audio_stream = None
                if stream:
                    try:
                        stream.stop_stream()
                        stream.close()
                    except Exception:
                        pass
                if manager:
                    try:
                        manager.terminate()
                    except Exception:
                        pass
                with self._audio_lock:
                    self._audio_latest[:] = 0
            self._stop_event.wait(2)
