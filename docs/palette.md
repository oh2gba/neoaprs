# The palette

The only place a colour is written in `ui/src` is `ui/src/styles/tokens.css` (the map's own style, `ui/src/lib/basemapstyle.ts`, and the map layers that read these tokens, `ui/src/lib/*layers.ts`, are the listed exceptions; `ui/src/styles/palette.test.ts` fails for a colour literal anywhere else). Every token has a value for the light and for the dark theme. This table is held to the file by that test.

Tags (`TagMark`) use only the soft pairs, by meaning: a count is **accent**, a label **neutral**, a state **ok**, **warn**, **bad** or **info**, what is made up (the Dummy radio) **neutral** with a dashed border. The strong colours are for a line, a word, or the rare loud fill.

| token | light | dark | for |
|---|---|---|---|
| `--bg` | `#f4f5f3` | `#14171a` | the page behind |
| `--panel` | `#ffffff` | `#1c2024` | a surface (the panel, a form, a card) |
| `--raised` | `#ffffff` | `#232930` | what stands over a surface: a note, a menu |
| `--text` | `#1d2125` | `#e3e6e8` | text |
| `--muted` | `#5d6670` | `#98a2ab` | quiet text, a label, a line |
| `--border` | `#d3d7da` | `#343a40` | the lines between things |
| `--row-hover` | `#eef3f9` | `#252b31` | a row under the pointer |
| `--row-selected` | `#d9e7f8` | `#24395a` | the selected row |
| `--input-bg` | `#ffffff` | `#14171a` | the inside of an input |
| `--accent` | `#1565c0` | `#6aa9ee` | the one accent, the blue: a primary button, the selected tab, a link |
| `--accent-text` | `#ffffff` | `#0b1a2b` | the text read on the accent |
| `--ok` | `#2e7d32` | `#66bb6a` | strong green: a line, a word, a loud fill |
| `--warn` | `#b26a00` | `#ffb74d` | strong amber |
| `--bad` | `#c62828` | `#ef5350` | strong red (Daemon offline, a destructive button) |
| `--info` | `#00697f` | `#4dc4de` | strong teal |
| `--on-strong` | `#ffffff` | `#ffffff` | the text read on a strong fill |
| `--on-strong-wash` | `rgb(255 255 255 / 20%)` | `rgb(255 255 255 / 20%)` | a hover on a strong fill |
| `--accent-soft-bg` | `#dce8f8` | `#1c3555` | the accent tag: the background |
| `--accent-soft-fg` | `#0d4a94` | `#aacdf6` | the accent tag: the text (AA at 11 px) |
| `--ok-soft-bg` | `#e2f0e3` | `#1f3a24` | the ok tag: the background |
| `--ok-soft-fg` | `#1b5e20` | `#a5d6a7` | the ok tag: the text (AA at 11 px) |
| `--warn-soft-bg` | `#fbe9c8` | `#41310f` | the warn tag: the background |
| `--warn-soft-fg` | `#764600` | `#ffcc80` | the warn tag: the text (AA at 11 px) |
| `--bad-soft-bg` | `#fbe0e0` | `#4a2323` | the bad tag: the background |
| `--bad-soft-fg` | `#9b1c1c` | `#f2a5a5` | the bad tag: the text (AA at 11 px) |
| `--info-soft-bg` | `#dcedf5` | `#163744` | the info tag: the background |
| `--info-soft-fg` | `#0b5570` | `#86d6ea` | the info tag: the text (AA at 11 px) |
| `--neutral-soft-bg` | `#e9ecee` | `#2a3036` | the neutral tag: the background |
| `--neutral-soft-fg` | `#454f58` | `#b6c0c9` | the neutral tag: the text (AA at 11 px) |
| `--scrim` | `rgba(0, 0, 0, 0.45)` | `rgba(0, 0, 0, 0.45)` | the veil behind a dialog |
| `--map-label` | `#1d2125` | `#e3e6e8` | the map: text |
| `--map-halo` | `rgba(255, 255, 255, 0.9)` | `rgba(20, 23, 26, 0.9)` | the map: the halo of text |
| `--map-ring` | `#ffffff` | `#ffffff` | the map: the ring of a plain marker |
| `--map-sign-bg` | `#ffd600` | `#ffd600` | the map: a signpost |
| `--map-sign-ink` | `#000000` | `#000000` | the map: the text of a signpost |
| `--map-select` | `#ff6d00` | `#ff6d00` | the map: the selected station and its track |
| `--map-select-wash` | `rgba(255, 109, 0, 0.18)` | `rgba(255, 109, 0, 0.18)` | the map: the wash of the selected station |
| `--map-plate` | `rgba(255, 255, 255, 0.88)` | `rgba(255, 255, 255, 0.88)` | the map: the plate under a symbol in the dark theme |
| `--map-track` | `#2f80ed` | `#2f80ed` | the map: a track |
| `--wx-temp` | `#d84315` | `#ff8a65` | the weather graphs: temperature |
| `--wx-pressure` | `#7b1fa2` | `#ce93d8` | the weather graphs: pressure |
| `--wx-wind` | `#00838f` | `#4dd0e1` | the weather graphs: wind |
| `--wx-rain` | `#1565c0` | `#64b5f6` | the weather graphs: rain |
