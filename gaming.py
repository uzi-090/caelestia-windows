"""Read-only automatic Windows game/presentation guard.

SHQueryUserNotificationState and limited-rights foreground process inspection
are documented Windows APIs. GameConfigStore is an additional best-effort
Windows inventory: its registry layout is not a supported complete game API.
No game process is injected, modified, suspended or controlled by this module.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import ntpath
import os
from pathlib import Path
import time

try:
    import winreg
except ImportError:  # Allows deterministic policy tests outside Windows.
    winreg = None


class WindowsGameGuard:
    """Return a reason to hide the dashboard, or an empty string to allow it.

    The caller owns the fast polling cache and geometric fullscreen detection.
    This class caches registry inventory and filesystem/path decisions for 30s.
    """

    CACHE_SECONDS = 30.0
    _DESKTOP_CLASSES = frozenset({
        'progman', 'workerw', 'shell_traywnd', 'shell_secondarytraywnd',
    })
    _NON_GAME_EXES = frozenset({
        'chrome.exe', 'msedge.exe', 'firefox.exe', 'brave.exe', 'opera.exe',
        'opera_gx.exe', 'vivaldi.exe', 'iexplore.exe', 'browser.exe',
        'msedgewebview2.exe', 'steamwebhelper.exe', 'epicwebhelper.exe',
        'unrealcefsubprocess.exe', 'cefsubprocess.exe',
        'steam.exe', 'steamservice.exe', 'epicgameslauncher.exe',
        'epiconlineservices.exe', 'epiconlineservicesuserhelper.exe',
        'gamingservices.exe', 'gamingservicesnet.exe', 'gamingapp.exe',
        'xboxapp.exe', 'gamebar.exe', 'gamebarftserver.exe',
        'gamebarpresencewriter.exe', 'unrealeditor.exe', 'ue4editor.exe',
    })
    _SHELL_REASONS = {
        1: 'Windows session is locked or unavailable',
        2: 'Windows is busy with a fullscreen app or presentation',
        3: 'Exclusive fullscreen Direct3D app',
        4: 'Windows presentation mode',
    }

    def __init__(self):
        self._user32 = None
        self._kernel32 = None
        self._shell32 = None
        self._registered_games: frozenset[str] = frozenset()
        self._registry_refreshed = float('-inf')
        self._path_cache: dict[str, tuple[float, str]] = {}
        if os.name == 'nt':
            self._init_windows_api()

    def _init_windows_api(self) -> None:
        # API/permission failures never prevent the dashboard from starting.
        try:
            user = ctypes.WinDLL('user32.dll', use_last_error=True)
            kernel = ctypes.WinDLL('kernel32.dll', use_last_error=True)
            user.GetForegroundWindow.argtypes = []
            user.GetForegroundWindow.restype = wintypes.HWND
            user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
            user.GetClassNameW.restype = ctypes.c_int
            user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
            user.GetWindowThreadProcessId.restype = wintypes.DWORD
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                        wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
            kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle.restype = wintypes.BOOL
            self._user32, self._kernel32 = user, kernel
        except (OSError, AttributeError):
            pass
        try:
            shell = ctypes.WinDLL('shell32.dll', use_last_error=True)
            shell.SHQueryUserNotificationState.argtypes = [ctypes.POINTER(ctypes.c_int)]
            shell.SHQueryUserNotificationState.restype = ctypes.c_long  # HRESULT
            self._shell32 = shell
        except (OSError, AttributeError):
            pass

    def _query_shell_state(self) -> int:
        if self._shell32 is None:
            return 0
        state = ctypes.c_int()
        try:
            if self._shell32.SHQueryUserNotificationState(ctypes.byref(state)) == 0:
                return state.value
        except (OSError, ValueError, AttributeError):
            pass
        return 0

    def _foreground_image(self, own_hwnd: int) -> str:
        if self._user32 is None or self._kernel32 is None:
            return ''
        process = None
        try:
            hwnd = self._user32.GetForegroundWindow()
            if not hwnd or int(hwnd) == int(own_hwnd or 0):
                return ''
            window_class = ctypes.create_unicode_buffer(256)
            self._user32.GetClassNameW(hwnd, window_class, len(window_class))
            if window_class.value.casefold() in self._DESKTOP_CLASSES:
                return ''
            pid = wintypes.DWORD()
            self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if not pid.value or pid.value == os.getpid():
                return ''
            # PROCESS_QUERY_LIMITED_INFORMATION; no process memory, injection,
            # debugging, write or control rights are requested.
            process = self._kernel32.OpenProcess(0x1000, False, pid.value)
            if not process:
                return ''
            filename = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(filename))
            if self._kernel32.QueryFullProcessImageNameW(process, 0, filename, ctypes.byref(size)):
                return filename.value
        except (OSError, ValueError, AttributeError):
            pass
        finally:
            if process:
                self._kernel32.CloseHandle(process)
        return ''

    @staticmethod
    def _normalize_path(filename: str) -> str:
        path = ntpath.normpath(os.path.expandvars(str(filename).strip().strip('"')))
        if path.startswith('\\\\?\\'):
            path = path[4:]
        return ntpath.normcase(path).casefold()

    def _refresh_registered_games(self, now: float) -> None:
        if now - self._registry_refreshed < self.CACHE_SECONDS:
            return
        self._registry_refreshed = now
        paths: set[str] = set()
        if winreg is not None:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                    r'System\GameConfigStore\Children', 0, winreg.KEY_READ) as inventory:
                    count = winreg.QueryInfoKey(inventory)[0]
                    for index in range(count):
                        try:
                            name = winreg.EnumKey(inventory, index)
                            with winreg.OpenKey(inventory, name, 0, winreg.KEY_READ) as game:
                                # Windows builds differ. The current host uses
                                # MatchedExeFullPath; accept both observed names.
                                for value_name in ('MatchedExeFullPath', 'MatchExeFullPath'):
                                    try:
                                        value, kind = winreg.QueryValueEx(game, value_name)
                                        if kind in (winreg.REG_SZ, winreg.REG_EXPAND_SZ) and isinstance(value, str):
                                            path = self._normalize_path(value)
                                            if ntpath.isabs(path) and path.endswith('.exe'):
                                                paths.add(path)
                                    except OSError:
                                        continue
                        except OSError:
                            continue
            except OSError:
                pass
        registered = frozenset(paths)
        if registered != self._registered_games:
            self._path_cache.clear()
        self._registered_games = registered

    @staticmethod
    def _has_gdk_manifest(filename: str) -> bool:
        try:
            directory = Path(filename).parent
            # The executable's own folder and at most four ancestors. This is
            # a bounded metadata check, never a drive scan or content search.
            for _ in range(5):
                if (directory / 'MicrosoftGame.config').is_file():
                    return True
                parent = directory.parent
                if parent == directory:
                    break
                directory = parent
        except (OSError, ValueError):
            pass
        return False

    def _game_path_reason(self, filename: str, now: float | None = None) -> str:
        now = time.monotonic() if now is None else now
        path = self._normalize_path(filename)
        basename = ntpath.basename(path)
        if not ntpath.isabs(path) or not basename.endswith('.exe') or basename in self._NON_GAME_EXES:
            return ''
        self._refresh_registered_games(now)
        cached = self._path_cache.get(path)
        if cached is not None and now - cached[0] < self.CACHE_SECONDS:
            return cached[1]
        reason = ''
        if path in self._registered_games:
            reason = f'Registered game: {basename}'
        elif basename in {'cod.exe', 'codhq.exe'}:
            reason = f'Call of Duty: {basename}'
        elif basename.endswith('-win64-shipping.exe'):
            reason = f'Unreal game: {basename}'
        else:
            parts = path.split('\\')
            if any(a == 'steamapps' and b == 'common' for a, b in zip(parts, parts[1:])):
                reason = f'Steam game: {basename}'
            elif 'xboxgames' in parts:
                reason = f'Xbox game: {basename}'
            else:
                for index, part in enumerate(parts[:-2]):
                    if part in {'epicgames', 'epic games'}:
                        folder = parts[index + 1]
                        if folder not in {'launcher', 'epicgameslauncher', 'epiconlineservices', 'epic online services'} and not folder.startswith('ue_'):
                            reason = f'Epic game: {basename}'
                            break
            if not reason and self._has_gdk_manifest(filename):
                reason = f'Windows game: {basename}'
        if len(self._path_cache) >= 1024:
            self._path_cache.clear()
        self._path_cache[path] = (now, reason)
        return reason

    def block_reason(self, own_hwnd: int) -> str:
        """Read current Windows/foreground state without changing it."""
        try:
            reason = self._SHELL_REASONS.get(self._query_shell_state(), '')
            if reason:
                return reason
            filename = self._foreground_image(own_hwnd)
            return self._game_path_reason(filename) if filename else ''
        except (OSError, ValueError, TypeError, AttributeError):
            return ''
