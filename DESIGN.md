# Design notes

This independent Windows companion adapts the upstream Caelestia layout and motion language. The four-page panel opens at the top center and smoothly changes dimensions between pages. Upstream credits and licenses are preserved.

- Motion: original Caelestia 500 ms cubic curve (0.38, 1.21, 0.22, 1); slides from `-height-5`, opacity follows the same progress. Horizontal page travel and width/height changes use the same curve. Cover mask rotates counter-clockwise once per23.5 seconds while playing. Visualizer follows the actual scalloped shape boundary. Compact player's progress wave runs a2-second phase.
- Colour: derive Material-style primary, secondary and tertiary from the current wallpaper. The base is a blurred, spatially aligned copy of the wallpaper with a readable translucent surface. The top curves and panel share one continuous masked glass surface, including the wallpaper offset and tint; no separate solid-colour corner wedges. No fixed purple theme. Foreground, muted and outline values respond to the chosen palette.
- Type: Rubik for the video reference; Material Symbols Rounded for icons. Bundle font files locally; preserve original licenses.
- Layout: Dashboard839×435, Media1000×320, Performance1112×380, compact Weather720×400 before shared tabs/padding. Scale all dimensions uniformly against a1920px logical desktop width: Media occupies53.75% of the screen, matching the full-desktop reference. Header has four equal tabs with a moving underline. Preserve the original Performance module proportions, with restrained corner radii, quiet raised surfaces and an actual Material scalloped CPU badge. Battery has a narrow tinted track, an accurate animated charge level and status/percentage aligned to its bottom edge with nonoverlapping contrast masks.
- Data: live Windows system values; supported Windows media sessions; WASAPI output visualization; configurable weather in Celsius and km/h. Missing sensor/media fields stay unavailable rather than becoming invented values.
- Operation: no title bar, top-center hover activation, immediate closing animation on pointer exit (no close grace period), Escape hides, tray Show/Hide/Pin/Exit, Ctrl+Alt+D toggles. Keyboard/tray reveal waits for first pointer entry before enabling exit dismissal. Automatic gaming protection hides the whole native window (including the activation area), closes popup menus and releases the shortcut for fullscreen/borderless or recognized foreground games. Restore only the collapsed Qt.Tool window without activation, requiring pointer exit/re-entry. No manual pause option. No Windows startup change unless requested.

Validation: render every tab, compare with the documented layout proportions, exercise controls and hover/hide logic, verify actual audio response and the rotation/pause behavior, and capture a local motion preview. Report any remaining differences honestly.

Media refinement: settled text must render directly in the scene rather than
through a permanent panel texture. Use a group layer only for the entrance/exit
fade, pixel-align the panel and size effect textures for the display. Retain a
readable wallpaper-frosted base with a softer tint; this is not fully clear glass.
Preserve original artwork bytes and retry late media changes. Both pages use one
uncapped monotonic playback projection. Lyrics use a cached independent LRCLIB
lookup with duration/artist matching, animated line following and explicit
untimed/unavailable states; never pretend to read Spotify's private lyrics feed.
Optional Cover Art Archive enrichment must require a configured developer
contact for MusicBrainz, strictly match song metadata, retain original bytes,
reject stale-track results and never replace better native artwork.

Widget finish: apply only a restrained 80%-opaque surface, a 5.5% light edge
(3.5% for small forecast/detail cells), and a 2.5% top sheen to Dashboard,
Performance and Weather cards. Keep content fully opaque, preserve geometry and
animations, and retain the existing Media page and main wallpaper-based panel
background. Do not introduce a whole-panel native glass effect.
