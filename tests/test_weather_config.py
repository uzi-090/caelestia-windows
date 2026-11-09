import json
from pathlib import Path
import tempfile
import unittest

from weather_config import WeatherLocation, load_weather_location


class WeatherConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'settings.json'

    def save(self, **changes):
        weather = dict(city='Example City', country='Example Country',
                       latitude=40.7, longitude=-74.0, timezone='auto')
        weather.update(changes)
        self.path.write_text(json.dumps({'weather': weather}), 'utf-8')

    def test_missing_settings_use_public_example(self):
        self.assertEqual(load_weather_location(self.path), WeatherLocation())

    def test_user_location_is_loaded(self):
        self.save()
        location = load_weather_location(self.path)
        self.assertEqual(location.city, 'Example City')
        self.assertEqual(location.latitude, 40.7)

    def test_invalid_coordinates_are_rejected(self):
        for changes in ({'latitude': 100}, {'longitude': float('nan')},
                        {'latitude': True}, {'latitude': 10 ** 400}):
            with self.subTest(changes=changes):
                self.save(**changes)
                self.assertEqual(load_weather_location(self.path), WeatherLocation())

    def test_malformed_settings_are_rejected(self):
        for text in ('{broken', '[]', '{"weather": null}'):
            self.path.write_text(text, 'utf-8')
            self.assertEqual(load_weather_location(self.path), WeatherLocation())

    def test_oversized_settings_are_rejected(self):
        self.path.write_text(' ' * 16385, 'utf-8')
        self.assertEqual(load_weather_location(self.path), WeatherLocation())

    def test_cached_forecasts_are_separate_for_each_location(self):
        self.save()
        first = load_weather_location(self.path)
        self.save(latitude=41.0)
        second = load_weather_location(self.path)
        self.assertNotEqual(first.cache_name, second.cache_name)
        self.assertNotIn(first.city, first.cache_name)


if __name__ == '__main__':
    unittest.main()
