"""Local weather settings; no location detection or credentials are required."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re

LOG = logging.getLogger('caelestia.weather')


@dataclass(frozen=True)
class WeatherLocation:
    city: str = 'London'
    country: str = 'United Kingdom'
    latitude: float = 51.5074
    longitude: float = -0.1278
    timezone: str = 'auto'

    @property
    def cache_name(self) -> str:
        data = json.dumps(self.__dict__, sort_keys=True).encode('utf-8')
        return 'weather-' + hashlib.sha256(data).hexdigest()[:16] + '.json'


def load_weather_location(path: Path | None = None) -> WeatherLocation:
    if path is None:
        path = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'CaelestiaWindows' / 'settings.json'
    try:
        if path.stat().st_size > 16384:
            raise ValueError('Weather settings exceed size limit')
        weather = json.loads(path.read_text('utf-8'))['weather']
        city, country = weather['city'], weather['country']
        if not all(isinstance(value, str) and value.strip() and len(value) <= 80
                   for value in (city, country)):
            raise ValueError('Invalid city or country')
        if any(isinstance(weather[key], bool) for key in ('latitude', 'longitude')):
            raise ValueError('Invalid coordinates')
        latitude, longitude = float(weather['latitude']), float(weather['longitude'])
        if not (math.isfinite(latitude) and -90 <= latitude <= 90
                and math.isfinite(longitude) and -180 <= longitude <= 180):
            raise ValueError('Coordinates out of range')
        timezone = weather.get('timezone', 'auto')
        if not isinstance(timezone, str) or not re.fullmatch(r'[A-Za-z0-9_+./-]{1,64}', timezone):
            raise ValueError('Invalid timezone')
        return WeatherLocation(city.strip(), country.strip(), latitude, longitude, timezone)
    except FileNotFoundError:
        return WeatherLocation()
    except (OSError, ValueError, KeyError, TypeError, OverflowError):
        LOG.warning('Invalid local weather settings; using the example location')
        return WeatherLocation()
