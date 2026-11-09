"""Core policy tests: game detection must not classify ordinary browsers/apps."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gaming import WindowsGameGuard


def guard():
    value = WindowsGameGuard()
    value._refresh_registered_games = Mock()
    value._has_gdk_manifest = Mock(return_value=False)
    return value


class GameGuardPolicy(unittest.TestCase):
    def test_known_game_signatures(self):
        value = guard()
        for path in (
            r'C:\SteamLibrary\steamapps\common\Apex Legends\r5apex.exe',
            r'D:\XboxGames\Game\Content\Game.exe',
            r'D:\Epic Games\Fortnite\FortniteGame\Binaries\Win64\Fortnite.exe',
            r'D:\EpicGames\RocketLeague\Binaries\Win64\RocketLeague.exe',
            r'D:\Games\Call of Duty\cod.exe',
            r'D:\Games\Call of Duty\codhq.exe',
            r'D:\Custom\Project-Win64-Shipping.exe',
        ):
            with self.subTest(path=path):
                self.assertTrue(value._game_path_reason(path, 100))

    def test_browsers_launchers_and_editors_are_not_games(self):
        value = guard()
        for path in (
            r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Steam\steamapps\common\Game\chrome.exe',
            r'C:\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe',
            r'C:\Epic Games\Launcher\Engine\Binaries\Win64\helper.exe',
            r'C:\Epic Games\UE_5.6\Engine\Binaries\Win64\UnrealEditor.exe',
            r'C:\Apps\Visual Studio Code\Code.exe',
            r'C:\Program Files\Java\bin\javaw.exe',
        ):
            with self.subTest(path=path):
                self.assertEqual(value._game_path_reason(path, 100), '')

    def test_registered_java_requires_exact_full_path(self):
        value = guard()
        registered = r'C:\Prism\runtimes\java21\bin\javaw.exe'
        value._registered_games = frozenset({value._normalize_path(registered)})
        self.assertTrue(value._game_path_reason(registered.upper(), 100))
        self.assertEqual(value._game_path_reason(r'C:\OtherJava\bin\javaw.exe', 100), '')
        chrome = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
        value._registered_games = frozenset({value._normalize_path(chrome)})
        self.assertEqual(value._game_path_reason(chrome, 100), '')

    def test_file_decision_cache_has_bounded_lifetime(self):
        value = guard()
        path = r'C:\Custom\WindowedGame\game.exe'
        self.assertEqual(value._game_path_reason(path, 100), '')
        value._has_gdk_manifest.return_value = True
        self.assertEqual(value._game_path_reason(path, 110), '')
        self.assertTrue(value._game_path_reason(path, 131))
        self.assertEqual(value._has_gdk_manifest.call_count, 2)

    def test_notification_state_and_graceful_api_failure(self):
        value = guard()
        value._foreground_image = Mock(return_value='')
        for state in (1, 2, 3, 4):
            value._query_shell_state = Mock(return_value=state)
            self.assertTrue(value.block_reason(1234))
        for state in (0, 5, 6, 7):
            value._query_shell_state = Mock(return_value=state)
            self.assertEqual(value.block_reason(1234), '')
        value._foreground_image.side_effect = OSError('limited query access denied')
        self.assertEqual(value.block_reason(1234), '')

    def test_path_case_and_extended_prefix(self):
        value = guard()
        self.assertTrue(value._game_path_reason(r'\\?\D:\Steam\SteamApps\Common\Game\game.EXE', 100))
        self.assertEqual(value._game_path_reason('cod.exe', 100), '')


if __name__ == '__main__':
    unittest.main(verbosity=2)
