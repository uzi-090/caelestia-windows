# Privacy and local data

The public source contains no user configuration, media cache, logs, credentials,
personal wallpapers, desktop recordings or Linux/disk backups. The default
weather city is a public example, not a detected location.

## On your computer

Runtime files are stored in `%LOCALAPPDATA%\CaelestiaWindows`, outside this
repository. These include logs, locally fitted wallpaper images, forecasts,
media artwork and lyrics caches. `settings.json` supplies your chosen weather
location. `cache/artwork-contact.json` optionally supplies a developer contact
for album-art lookup. Do not commit either file.

Windows media sessions supply the track information that the selected player
chooses to expose. The visualizer analyzes default-output audio in memory;
it does not save recordings or upload audio. The app reads local system
statistics and checks the foreground app for automatic gaming protection.

## Network requests

| Service | What is sent | Purpose |
| --- | --- | --- |
| Open-Meteo | The configured coordinates and forecast options | Weather forecast |
| LRCLIB | Available song title, artist, album and duration | Matching lyrics |
| MusicBrainz / Cover Art Archive | Song metadata and the configured developer contact | Optional high-resolution artwork; disabled until configured |

There is no analytics service, advertising identifier, account login, bundled
API key, browser-history reader, or cookie reader. Network requests still expose
the connecting IP address to their destination services. Consult those services'
own privacy terms when using them.

Logs and cached media may contain local file paths, device names and track
information. Review and redact these before sharing a bug report. The developer
options for captures can also save live app data; keep those outputs private.
