# GUI appearance, language and credits

## Preferences

Settings → General → Appearance and language offers native GTK system/light/dark
appearance and system/English/Turkish/Azerbaijani language selection. Existing
configuration files without a UI section keep working with system defaults.

```toml
[ui]
theme = "system"   # system | light | dark
language = "system"   # system | en | tr | az
```

Themes apply immediately. GTK's preferred dark variant is used rather than
forcing a theme name. On GNOME, the system option follows changes to
`org.gnome.desktop.interface`'s `color-scheme`; otherwise the initial GTK
preference is used. CSS derives surfaces and foregrounds from native theme
colors. Other-desktop live preference integration remains a follow-up.

Language changes require an application restart. Saving does not rebuild pages,
discard edited forms or interrupt a running scan. At launch the language is
selected before pages are constructed. `LANGUAGE` supplies a priority list,
followed by `LC_ALL`, `LC_MESSAGES` or `LANG`. Unsupported system locales use
English. Explicit choices override the environment.

Preferences share the existing private, atomic TOML save path. If saving fails,
the controls and in-memory preferences revert before a theme or live-presence
service change is applied. Network and policy settings are preserved.

## Translation maintenance

`core.i18n` is independent of GTK. English source messages are stable lookup
keys in `core/locales/en.json`, `tr.json` and `az.json`. Translate presentation
text with `tr(message, **values)`. Format values after lookup, keep placeholder
names/conversions/specifiers intact, and keep machine IDs separate from labels.
Names, addresses, protocols, user descriptions, historical events and backend
diagnostic details remain original data. A translated wrapper can describe the
operation around a raw diagnostic. Unknown messages fall back to the source.

To add a language, add its code/native label to `core.i18n`, allow it in
`UIConfig`, add a matching UTF-8 JSON catalog and expose it in Settings. The
tests check catalog key parity, placeholders, locale precedence and literal
GUI lookup coverage. Setuptools package data and PyInstaller's `--collect-data
core` include the catalogs in both distribution formats.

## About and small-window improvements

The About page reads `core.version.VERSION` and translates descriptions,
headings and link labels. Credits retain original developer Praxis1071 and add
contributor Cavanşir Qurbanzadə (YoungLion), linked to
https://github.com/Cavanshirpro. URLs, names and license identifiers are stable.

The header toggles navigation visibility. Dashboard and Monitoring metrics use
two columns; Profile/Rule creation forms use vertical layouts. Monitoring uses
an explicit paused flag, independent of button translations. Native switch
notifications persist the new active state rather than the previous state.
Dashboard labels describe desired policy and do not imply kernel enforcement.
These changes advance the GUI roadmap without completing the adaptive-layout
or Libadwaita migration gates.

## Validation and remaining graphical QA

The Python suite runs without GTK because importing `gui.state` does not import
the application. Preference callback tests execute the production bodies with
controlled widgets and real TOML persistence. These tests verify decisions and
save/error contracts, not graphical rendering. The wheel was built and all
three catalogs were loaded from its packaged resources in an isolated process.

Before merge, run a real GTK4 session and verify:

- Switch system/light/dark, restart and confirm saved selection and contrast.
- In system mode change GNOME's appearance and confirm live updates; verify
  high contrast using the distribution's native theme.
- Restart in each language and inspect all navigation/pages, dynamic statuses,
  mode/action selection and About links/version/credits.
- Exercise narrow and desktop windows, hide/show navigation and verify keyboard
  focus and access to all actions, including the Devices detail pane.
- Pause/resume Monitoring, toggle live presence, and provoke a preference-save
  failure to confirm controls, persisted values and service state agree.
- Run fresh CI, including native GTK imports and privileged network tests.
