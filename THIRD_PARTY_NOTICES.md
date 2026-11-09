# Third-party notices

This independent Windows adaptation includes or adapts the following projects.
Original copyright notices remain applicable. The application's GPL v3 text is
in `LICENSE`; asset licences are in `assets`. Bundled Python package metadata,
including the licence files supplied by their wheels, is under `_internal` in
the portable build. Corresponding application sources are in `source`.

| Component | Source and licence |
| --- | --- |
| Caelestia shell layouts, animation definitions, logo and Bongo Cat asset | [caelestia-dots/shell](https://github.com/caelestia-dots/shell), GNU GPL v3. The original shell is for Linux/Hyprland. |
| Material shape geometry | [soramanew/m3shapes](https://github.com/soramanew/m3shapes), Apache License 2.0; see `assets/m3shapes-LICENSE.txt`. |
| Rubik font | [Google Fonts Rubik](https://github.com/google/fonts/tree/main/ofl/rubik), SIL Open Font License 1.1; see `assets/Rubik-OFL.txt`. |
| Material Symbols Rounded | [Google Material Design icons](https://github.com/google/material-design-icons), Apache License 2.0; see `assets/MaterialSymbols-LICENSE.txt`. |
| Qt 6 / PySide6 / Shiboken | [Qt for Python](https://www.qt.io/qt-for-python), open-source LGPL v3 / GPL licence options as applicable to individual modules; [Qt source downloads](https://download.qt.io/official_releases/qt/), [PySide source](https://code.qt.io/cgit/pyside/pyside-setup.git/). Qt libraries are dynamically bundled and remain separate files. |
| CPython | [Python](https://www.python.org/), Python Software Foundation licence and included third-party notices; [Python licence](https://docs.python.org/3/license.html). |
| NumPy | [NumPy](https://numpy.org/), BSD 3-Clause and bundled dependency licences listed in its wheel metadata, including OpenBLAS where included. |
| psutil | [psutil](https://github.com/giampaolo/psutil), BSD 3-Clause. |
| PyAudioWPatch | [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch), Apache License 2.0, with upstream PyAudio/PortAudio notices supplied with that project. |
| PortAudio | [PortAudio](https://www.portaudio.com/), MIT-style PortAudio licence, bundled through PyAudioWPatch. |
| PyWinRT / WinRT projections | [PyWinRT](https://github.com/pywinrt/pywinrt), MIT. |
| Pillow | [Pillow](https://python-pillow.github.io/), MIT-CMU with applicable bundled image-library notices. |
| materialyoucolor | [materialyoucolor-python](https://github.com/T-Dynamos/materialyoucolor-python), MIT; includes/adapts Google's [Material Color Utilities](https://github.com/material-foundation/material-color-utilities), Apache License 2.0. |
| PyInstaller bootloader | [PyInstaller](https://pyinstaller.org/), GPL v2 or later with the bootloader distribution exception. Used to package the application. |
| Forecast data | [Open-Meteo](https://open-meteo.com/), weather data provided under [CC BY 4.0](https://open-meteo.com/en/terms). |
| Lyrics lookup | [LRCLIB API](https://lrclib.net/docs), queried at runtime using track metadata. Song lyrics are not bundled with the application. |
| Optional album-cover lookup | [MusicBrainz API](https://musicbrainz.org/doc/MusicBrainz_API) and [Cover Art Archive](https://musicbrainz.org/doc/Cover_Art_Archive/API), queried only when configured with a developer contact. MusicBrainz core metadata is CC0; cover images retain their respective rights. No album-cover catalogue is bundled. |

Other runtime components, including Windows runtime libraries, retain their own
licence terms. This document identifies dependencies; it does not replace their
licence texts or grant rights beyond the upstream licences.
