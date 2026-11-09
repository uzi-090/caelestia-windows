"""Read-only Windows wallpaper fitting, frosted wallpaper and adaptive palette.

The generated image is a blurred copy of the wallpaper, so the panel keeps
matching the wallpaper when other application windows are underneath it.
Nothing in this module changes the Windows wallpaper or personalization.
"""

from __future__ import annotations

import colorsys
import ctypes
import hashlib
import logging
import os
from pathlib import Path
import threading
import winreg

from PIL import Image, ImageColor, ImageFilter, ImageOps
from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot

log = logging.getLogger(__name__)


def _registry_value(path: str, name: str, default=""):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return default


def current_wallpaper() -> Path | None:
    """SPI_GETDESKWALLPAPER only: no mutation flags or setters are used."""
    buf = ctypes.create_unicode_buffer(32768)
    try:
        if ctypes.windll.user32.SystemParametersInfoW(0x0073, len(buf), buf, 0):
            path = Path(os.path.expandvars(buf.value))
            if path.is_file():
                return path
    except (AttributeError, OSError):
        pass
    raw = _registry_value(r"Control Panel\Desktop", "WallPaper")
    if raw:
        path = Path(os.path.expandvars(str(raw)))
        if path.is_file():
            return path
    # Windows keeps the current slideshow/Spotlight image here in some setups.
    cached = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Themes/TranscodedWallpaper"
    return cached if cached.is_file() else None


def _desktop_color() -> tuple[int, int, int]:
    raw = str(_registry_value(r"Control Panel\Colors", "Background", "18 20 22"))
    try:
        values = tuple(max(0, min(255, int(n))) for n in raw.split())
        return values if len(values) == 3 else (18, 20, 22)
    except ValueError:
        return 18, 20, 22


def _hex(rgb) -> str:
    return "#" + "".join(f"{round(max(0, min(255, v))):02x}" for v in rgb[:3])


def _rgb_hls(h: float, light: float, saturation: float) -> str:
    return _hex([v * 255 for v in colorsys.hls_to_rgb(h % 1, light, saturation)])


def _dominant_seed(image: Image.Image) -> tuple[int, int, int]:
    """Find a supported visible accent, without amplifying neutral scenery.

    Hue bins retain thin details that median-cut quantization can merge into
    dark borders. Population and actual RGB chroma both matter; relative HLS
    saturation helps a vivid dark accent compete with large muted foregrounds.
    A minimum population rejects isolated coloured pixels and JPEG noise.
    """
    small = ImageOps.exif_transpose(image).convert("RGB")
    small.thumbnail((320, 320), Image.Resampling.LANCZOS)
    bins = [[] for _ in range(36)]
    totals = [0, 0, 0]
    pixels = small.get_flattened_data() if hasattr(small, "get_flattened_data") else small.getdata()
    count = small.width * small.height
    if not count:
        return 128, 128, 128
    for color in pixels:
        for channel in range(3):
            totals[channel] += color[channel]
        hue, light, saturation = colorsys.rgb_to_hls(*(c / 255 for c in color))
        chroma = max(color) - min(color)
        if chroma >= 12 and 0.055 < light < 0.90:
            weight = chroma * saturation ** 1.5
            bins[int(hue * 36) % 36].append((color, weight))
    best_score, best = 0.0, None
    minimum_population = max(2, count * 0.0025)
    for index in range(36):
        cluster = bins[(index - 1) % 36] + bins[index] + bins[(index + 1) % 36]
        if len(cluster) < minimum_population:
            continue
        weight = sum(entry[1] for entry in cluster)
        strength = weight / len(cluster)
        if strength < 1.5:
            continue
        score = len(cluster) ** 0.55 * strength ** 1.9
        if score > best_score:
            best_score = score
            best = tuple(round(sum(color[channel] * w for color, w in cluster) / weight)
                         for channel in range(3))
    # A near-neutral wallpaper must not acquire an arbitrary vivid hue.
    return best or tuple(round(value / count) for value in totals)


def palette_for_image(image: Image.Image) -> dict:
    """Readable dark tones whose hue and chroma come from the wallpaper.

    TonalSpot intentionally imposes chroma 36, which turns even muted grey-green
    scenery into a bright green theme. These HCT roles instead retain the actual
    source chroma, with neutral surfaces and a restrained cap for vivid images.
    """
    seed = _dominant_seed(image)
    hue, _, saturation = colorsys.rgb_to_hls(*(c / 255 for c in seed))
    palette = {
        "background": _rgb_hls(hue, 0.072, min(0.18, saturation * 0.18)),
        "card": _rgb_hls(hue, 0.115, min(0.14, saturation * 0.16)),
        "cardAlt": _rgb_hls(hue, 0.165, min(0.17, saturation * 0.2)),
        "foreground": _rgb_hls(hue, 0.925, min(0.08, saturation * 0.1)),
        "muted": _rgb_hls(hue, 0.69, min(0.12, saturation * 0.2)),
        "primary": _rgb_hls(hue, 0.8, min(0.62, saturation * 0.72)),
        "secondary": _rgb_hls(hue, 0.78, min(0.3, saturation * 0.4)),
        "tertiary": _rgb_hls(hue, 0.82, min(0.42, saturation * 0.55)),
        "outline": _rgb_hls(hue, 0.3, min(0.1, saturation * 0.16)),
        "onPrimary": _rgb_hls(hue, 0.16, min(0.32, saturation * 0.5)),
        "seed": _hex(seed),
        "paletteAlgorithm": "wallpaper-hls-adaptive",
    }
    try:
        from materialyoucolor.hct import Hct
        argb = 0xFF000000 | seed[0] << 16 | seed[1] << 8 | seed[2]
        source = Hct.from_int(argb)
        chroma = min(42.0, source.chroma)
        roles = {
            "background": (6, min(3, chroma * 0.10)),
            "card": (10, min(3.5, chroma * 0.12)),
            "cardAlt": (15, min(4, chroma * 0.14)),
            "foreground": (90, min(3, chroma * 0.08)),
            "muted": (72, min(5, chroma * 0.16)),
            "primary": (80, chroma),
            "secondary": (78, chroma * 0.48),
            "tertiary": (82, chroma * 0.72),
            "outline": (30, min(5, chroma * 0.16)),
            "onPrimary": (18, chroma * 0.60),
        }
        for role, (tone, role_chroma) in roles.items():
            color = Hct.from_hct(source.hue, role_chroma, tone).to_int()
            palette[role] = f"#{color & 0xFFFFFF:06x}"
        palette["paletteAlgorithm"] = "wallpaper-hct-adaptive"
    except (ImportError, AttributeError, TypeError, ValueError, RuntimeError) as error:
        log.debug("Material You fallback: %s", error)
    return palette


def _fit_wallpaper(source: Image.Image, width: int, height: int, style: str,
                   tile: bool, background: tuple[int, int, int]) -> Image.Image:
    result = Image.new("RGB", (width, height), background)
    source = ImageOps.exif_transpose(source).convert("RGB")
    if tile:
        for y in range(0, height, source.height):
            for x in range(0, width, source.width):
                result.paste(source, (x, y))
        return result
    if style in ("10", "22"):  # Fill; span uses this screen's aspect ratio.
        return ImageOps.fit(source, (width, height), Image.Resampling.LANCZOS)
    if style == "6":  # Fit, centered with the Windows desktop color as padding.
        source = ImageOps.contain(source, (width, height), Image.Resampling.LANCZOS)
    elif style == "2":  # Stretch
        source = source.resize((width, height), Image.Resampling.LANCZOS)
    result.paste(source, ((width - source.width) // 2, (height - source.height) // 2))
    return result


class WallpaperService(QObject):
    changed = Signal()
    _prepared = Signal(dict)

    def __init__(self, width: int = 1920, height: int = 1080, parent=None):
        super().__init__(parent)
        self._width, self._height = max(1, int(width)), max(1, int(height))
        self._signature = None
        self._busy = False
        self._pending = False
        self._cache = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CaelestiaWindows/cache"
        self._cache.mkdir(parents=True, exist_ok=True)
        self._data = palette_for_image(Image.new("RGB", (4, 4), _desktop_color()))
        self._data.update(wallpaperUrl="", originalUrl="", width=self._width, height=self._height,
                          available=False, status="Loading wallpaper")
        self._prepared.connect(self._receive)
        self._timer = QTimer(self)
        self._timer.setInterval(15000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        QTimer.singleShot(0, self.refresh)

    @Property("QVariantMap", notify=changed)
    def data(self):
        return self._data

    @Slot()
    @Slot(int, int)
    def refresh(self, width=None, height=None):
        if width is not None and height is not None:
            self._width, self._height = max(1, int(width)), max(1, int(height))
        if self._busy:
            self._pending = True
            return
        source = current_wallpaper()
        style = str(_registry_value(r"Control Panel\Desktop", "WallpaperStyle", "10"))
        tile = str(_registry_value(r"Control Panel\Desktop", "TileWallpaper", "0")) == "1"
        background = _desktop_color()
        try:
            stat = source.stat() if source else None
            signature = (str(source), stat.st_mtime_ns if stat else 0,
                         stat.st_size if stat else 0, self._width, self._height,
                         style, tile, background)
        except OSError:
            return
        if signature == self._signature:
            return
        self._signature = signature
        self._busy = True
        threading.Thread(target=self._prepare,
                         args=(source, signature, self._width, self._height, style, tile, background),
                         name="Wallpaper", daemon=True).start()

    def _prepare(self, source, signature, width, height, style, tile, background):
        try:
            if source:
                with Image.open(source) as image:
                    rendered = _fit_wallpaper(image, width, height, style, tile, background)
            else:
                rendered = Image.new("RGB", (width, height), background)
            palette = palette_for_image(rendered)
            stamp = hashlib.sha256(repr(signature).encode()).hexdigest()[:16]
            original_path = self._cache / f"wallpaper-{stamp}.jpg"
            blurred_path = self._cache / f"frosted-{stamp}.jpg"
            if not original_path.is_file():
                rendered.save(original_path, quality=93)
            if not blurred_path.is_file():
                # Downsample before Gaussian blur for a smooth inexpensive frost.
                blur_scale = min(1.0, 1280 / width)
                small = rendered.resize((max(1, round(width * blur_scale)),
                                         max(1, round(height * blur_scale))), Image.Resampling.LANCZOS)
                small = small.filter(ImageFilter.GaussianBlur(28 * blur_scale))
                small = small.resize((width, height), Image.Resampling.BICUBIC)
                small.save(blurred_path, quality=90)
            palette.update(wallpaperUrl=blurred_path.as_uri(), originalUrl=original_path.as_uri(),
                           width=width, height=height, available=bool(source),
                           status="Ready" if source else "Desktop color", sourcePath=str(source or ""))
            self._prepared.emit(palette)
        except Exception as error:
            log.warning("Unable to prepare wallpaper: %s", error)
            result = dict(self._data)
            result["status"] = "Wallpaper unavailable"
            self._prepared.emit(result)

    @Slot(dict)
    def _receive(self, result):
        self._data = result
        self._busy = False
        self.changed.emit()
        if self._pending:
            self._pending = False
            self._signature = None
            self.refresh()
