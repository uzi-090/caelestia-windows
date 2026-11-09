# Caelestia for Windows

> Independent Windows adaptation of [Caelestia shell](https://github.com/caelestia-dots/shell). Not an official release or an endorsement by the upstream project.

**Windows 11 · Qt Quick · Python 3.12 · GPL-3.0**

This repository is a source release. Run from source using the instructions below, or build your own portable application. No prebuilt executable is included.

A native Windows 11 desktop dashboard adapted from Caelestia's design: hover at
the top middle of your display to reveal Dashboard, Media, Performance and
Weather. The panel uses Qt Quick with Direct3D 11, the original Rubik font and
Material Symbols, and Caelestia's animation curves and layout proportions.

## Open and use it

1. Open `CaelestiaWindows.exe` in the installed `app` folder, or use its desktop
   shortcut if one has been created. Keep the whole folder together; `_internal`
   contains its runtime and is required.
2. Move the cursor to the middle of the very top edge of your display. Move onto
   the panel to interact. Its closing animation starts immediately when the
   cursor leaves; there is no closing delay.
3. Click Dashboard, Media, Performance or Weather to change pages. The panel
   changes its size smoothly to fit each page.

The compact proportions follow the full-desktop reference: the Media page uses
about 54% of the display width. Top curves share the panel's frosted wallpaper
surface, and the Performance battery shows its actual charge level.

| Action | Shortcut or control |
| --- | --- |
| Show or hide the panel | `Ctrl+Alt+D`, or click the tray icon |
| Hide the panel | `Escape` while the panel has keyboard focus |
| Switch to Dashboard / Media / Performance / Weather | `Ctrl+1` / `Ctrl+2` / `Ctrl+3` / `Ctrl+4` while the panel has keyboard focus |
| Keep it open | Right-click the tray icon, then **Keep open** |
| Refresh wallpaper and forecast | Tray menu → **Refresh wallpaper and weather** |
| Close the app completely | Tray menu → **Exit** |

The tray icon may be inside the **^** overflow next to the Windows clock.
Gaming protection is automatic and has no pause switch. Fullscreen/borderless
apps, Windows fullscreen/presentation states and recognized foreground games
hide the entire panel window, including its activation area. Its shortcut is
released during protection. Returning to the desktop restores the collapsed
panel; leave and re-enter the top edge to reveal it again. Registered games and
common game install locations also cover many windowed games. An unrecognized
windowed game may not be detected; fullscreen/borderless protection still works.

## Wallpaper and colours

The panel reads your current Windows wallpaper, creates a blurred copy for its
soft translucent surface, and derives its accent colours automatically. It keeps matching
the wallpaper when other apps are behind it. Change the wallpaper in Windows
normally; the dashboard refreshes it automatically. It does not change your
wallpaper, taskbar, Windows login screen or boot configuration.

Dashboard, Performance and Weather widgets have a restrained glass finish with
a soft highlight and a faint edge. Text stays opaque and sharp. The Media page
and the main panel background retain their existing appearance.

## Music and video

The circular visualizer reacts to audio on the current default Windows output.
Apps that publish Windows media sessions can supply titles, artwork, playback
position and controls. This includes Spotify and YouTube in supported browsers;
support in VLC and other players depends on their Windows media integration.
Use the player selector when more than one session is present. The exact
information and controls available depend on what the selected app exposes.
An app can play sound without providing track metadata.

Audio is analysed in memory for the visualizer. It is not recorded to a file or
uploaded. Output-device changes are detected automatically. Separately routed
audio devices are not combined into one spectrum.

Both players share a continuously projected playback clock, including when a
player sends position snapshots infrequently. Artwork is retried when it arrives
late, stored from the original image bytes, and refreshed when a track changes.
Its detail still depends on the source image supplied by the player. Browsers
that intentionally hide media metadata cannot supply a real song title or cover.

An optional high-resolution album-cover lookup uses MusicBrainz and Cover Art
Archive for strictly matched songs. It only replaces smaller artwork, verifies
title, artist and duration, and retains the native image when no match exists.
This service requires a real developer contact email in its request headers.
It stays disabled unless `cache/artwork-contact.json` in the app's local data
folder contains an explicitly supplied `contactEmail`. When enabled, song
metadata and that contact address are sent to these services; cover results are
cached locally. It does not inspect browser history, cookies or accounts.

The Lyrics pane looks up matching music in **LRCLIB**. Timed lyrics follow the
song with an animated highlight and scroll; untimed lyrics are labelled and can
be scrolled normally. Scroll manually to inspect another part, then click
**Follow** to return to the current line. Clicking a timed line seeks when the
selected player supports seeking. Lyrics follow pauses and seeks automatically.
Use **Refresh media** in the three-dot menu to retry a lookup.

For lookup, the app sends the song title, artist, album and duration to LRCLIB
and keeps a small local cache. No Spotify account, browser cookies or audio are
sent. LRCLIB's catalogue is independent of Spotify's in-app lyrics; availability
can differ. Missing lyrics and instrumental tracks have explicit states.

## System information and weather

Performance shows live processor, memory, disk, network and battery data. Choose
a drive from the storage selector. CPU temperature is shown as unavailable when
Windows does not expose a supported sensor; there is no fabricated temperature.

Weather uses **London as a public example**, in **°C** and **km/h**. It does not automatically determine your location. Open-Meteo supplies
current conditions and the seven-day forecast. The forecast is refreshed every
20 minutes. A saved forecast remains available while offline and is marked as
such. Network requests supply weather and lyrics; audio stays on your computer.

To select your city, copy `settings.example.json` to `%LOCALAPPDATA%\CaelestiaWindows\settings.json`, edit the city, country and coordinates, then restart the app. Keep `timezone` set to `auto` for local forecast times. Your settings and forecasts stay outside the repository. See [PRIVACY.md](PRIVACY.md) for local storage and network requests.

## If something does not appear

- Use `Ctrl+Alt+D` or the tray menu if the top edge is hard to reach.
- If the shortcut is already used by another app, the tray and hover still work.
- If there is no music information, start playback in a media app and check the
  player selector. Missing artwork may simply mean the player has not supplied it.
- If the visualizer is still, check that sound is playing through the default
  Windows output. Protected media or exclusive-mode audio may not be available
  through Windows loopback capture.
- The diagnostic log is `%LOCALAPPDATA%\CaelestiaWindows\dashboard.log`.

The app does not currently register itself to start with Windows. Closing the
dashboard panel does not exit the background app; use **Exit** in the tray menu.

## Run or build from source

Clone or download this repository and open PowerShell in its root folder. Python 3.12 on 64-bit Windows is used for this build. Use a short runtime path to
avoid Windows path-length limits. From PowerShell, with Python already installed:

```powershell
python -m venv "$env:USERPROFILE\.cache\caelestia-windows\runtime"
& "$env:USERPROFILE\.cache\caelestia-windows\runtime\Scripts\python.exe" -m pip install -r requirements.txt pyinstaller==6.22.3
& "$env:USERPROFILE\.cache\caelestia-windows\runtime\Scripts\python.exe" main.py
```

To rebuild the portable app:

```powershell
.\build.ps1
```

The output is `%LOCALAPPDATA%\CaelestiaWindows\app\CaelestiaWindows.exe`. Exit the
packaged app before rebuilding. The build script only replaces a previous output
folder carrying this app's marker. It does not configure startup or Windows
security settings. The `source` folder beside the executable contains the
application sources, QML and assets used for the build.

## Development checks

With the same environment used above:

```powershell
& "$env:USERPROFILE\.cache\caelestia-windows\runtime\Scripts\python.exe" -m unittest discover -s tests -v
```

The regression suite uses mocked media/network data and does not control a real player. Assets and their licenses are committed; `python prepare_assets.py` checks their integrity without downloading files. Runtime caches, user settings, recordings, build output and virtual environments are excluded by `.gitignore`.

## Attribution

This is an independent Windows adaptation, not an official Windows release by
the Caelestia project. Application adaptations are licensed under GNU GPL v3;
see `LICENSE` and `THIRD_PARTY_NOTICES.md` for upstream projects and dependency
licences. Qt and other runtime libraries are included as separate dynamic files.
