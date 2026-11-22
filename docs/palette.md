# The palette

The only place a colour is written in `ui/src` is `ui/src/styles/tokens.css` (the map's own style, `ui/src/lib/basemapstyle.ts`, and the map layers that read these tokens, `ui/src/lib/*layers.ts`, are the listed exceptions; `ui/src/styles/palette.test.ts` fails for a colour literal anywhere else). Every token has a value for the light and for the dark theme. These tables are held to the file by that test.

The colours are the project page's (`site/style.css`): petrol `#0a2a3d`, `#0e1f2c`, `#182a34`; white, `#eff0f2`, `#5d5d5d`; mint `#a6d7d4`, sage `#91c1b9`; sky `#bbdaed`, blue `#60addb`, `#2972a3`; lime `#dbf93a`; orange `#fb6432`, `#e54615`. A tone is one of them, one of them mixed toward another ("x% toward"), or one laid on the theme's own ground, white or petrol, at a lower alpha ("x% on"); the file writes the solid result and the recipe beside it. The dark theme is the site's: the page `#0e1f2c`, the panel `#0a2a3d`.

The palette has no green, no amber and no red. **Ok** is the plain text, with its check mark where the page has one; **warn** is never a word in the bare `--warn` but a plate, the soft pair `--warn-soft-*` (the same pair as the tag): in the light theme petrol on a lime plate, in the dark theme lime on a dark lime plate, so that the plate stays darker than the HF tag's mint one. The plate is a shadow round the word's own box, so nothing moves; a line of its own (a refused Ask in Nearby, a short QRU in Objects) is as wide as its words, its plate widened sideways only. **bad** is the orange.

Tags (`TagMark`) use only the soft pairs, by meaning: a count is **accent**, a label **neutral**, a state **ok**, **warn**, **bad** or **info**, what is made up (the Dummy radio) **neutral** with a dashed border. The Mercury radio's tag is the site's inverse pill (`--hf-soft-*`: a petrol plate with white in the light theme, a mint one with petrol in the dark), told from every other tag by its lightness; the FM radio's tag is the neutral; the LoRa radio's is the sage (`--lora-soft-*`). The strong colours are for a line, a word, or the rare loud fill.

Every tone that stands as a small word (`--text`, `--muted`, `--accent`, `--ok`, `--bad`, and the Dummy's `--neutral-soft-fg`) reads at 4.5 to 1 on the panel, the page, a selected and a hovered row, a raised note and an input, in both themes, and on a group while it flashes (`--attention-bg`); every word on a plate reads at 4.5 to 1 on it; a drag across text (`--selection`) has the text at 4.5 to 1 and is told from every ground. The map, the weather graphs, the waterfall, the level bar, the phone code and the symbol sprites keep their own colours.

| token | light | dark | recipe | for |
|---|---|---|---|---|
| `--bg` | `#eff0f2` | `#0e1f2c` | the site's grey / the site's dark page | the page behind |
| `--panel` | `#ffffff` | `#0a2a3d` | white / petrol: the site's dark surface | a surface (the panel, the header, a form, a card) |
| `--raised` | `#ffffff` | `#1b394b` | white / white 7% on petrol | what stands over a surface: a note, a menu |
| `--text` | `#0a2a3d` | `#ffffff` | petrol / white | text |
| `--muted` | `#5d5d5d` | `#91c1b9` | the site's grey text / sage: the site's dark muted | quiet text, a label, a line |
| `--border` | `#d8dde0` | `#2c4858` | petrol 16% on white: the site's rule / white 14% on petrol: the site's rule | the lines between things |
| `--row-hover` | `#eef6fb` | `#193749` | sky 25% on white / white 6% on petrol | a row under the pointer |
| `--row-selected` | `#ddedf6` | `#173e55` | sky 50% on white / blue #60addb 15% on petrol | the selected row, our own bubble |
| `--selection` | `#bbdaed` | `#2c5e7c` | sky / blue #60addb 40% on petrol | a drag across text (with `--text` on it): told from every ground it is dragged over, the selected row and our own bubble among them |
| `--input-bg` | `#ffffff` | `#0e1f2c` | white / the site's dark page | the inside of an input |
| `--accent` | `#266b99` | `#60addb` | blue #2972a3 10% toward petrol / blue | the one accent, the blue: a primary button, the selected tab, a link, a tickbox, our own packets |
| `--accent-text` | `#ffffff` | `#0e1f2c` | white / the site's dark page | the text read on the accent |
| `--ok` | `#0a2a3d` | `#ffffff` | the plain text | ok: the plain text (the word says it, with its check mark); a line |
| `--warn` | `#dbf93a` | `#dbf93a` | lime: a line or a plate, never a word | warn: a line or a plate, never a word (a warn word is the soft pair) |
| `--bad` | `#b9401d` | `#fc8b65` | orange #e54615 20% toward petrol / orange #fb6432 25% toward white | bad, the orange: a word, a line, a loud fill (Daemon offline, a destructive button) |
| `--info` | `#2972a3` | `#bbdaed` | blue / sky | info: a line |
| `--on-strong` | `#ffffff` | `#0a2a3d` | white / petrol on the light fills of the dark theme | the text read on a strong fill |
| `--on-strong-wash` | `rgb(255 255 255 / 20%)` | `rgb(10 42 61 / 20%)` | white 20% / petrol 20% | a hover on a strong fill |
| `--accent-soft-bg` | `#dfeff8` | `#224f69` | blue #60addb 20% on white / blue #60addb 28% on petrol | the accent tag (a count): the plate |
| `--accent-soft-fg` | `#205c84` | `#bbdaed` | blue #2972a3 30% toward petrol / sky | the accent tag: the text (AA at 11 px) |
| `--ok-soft-bg` | `#cae7e5` | `#294d5b` | mint 60% on white / mint 20% on petrol | the ok tag: the plate |
| `--ok-soft-fg` | `#0a2a3d` | `#a6d7d4` | petrol / mint | the ok tag: the text (AA at 11 px) |
| `--warn-soft-bg` | `#dbf93a` | `#304f3c` | lime / lime 18% on petrol | the warn tag, and the plate of every warn word: the plate |
| `--warn-soft-fg` | `#0a2a3d` | `#dbf93a` | petrol / lime | the warn tag and a warn word: the text (AA at 11 px) |
| `--attention-bg` | `#f1fdb0` | `#1f3f3d` | lime 40% on white / lime 10% on petrol | the flash of a group that a link to a setting brought into view |
| `--bad-soft-bg` | `#fee0d6` | `#3f373b` | orange #fb6432 20% on white / orange #fb6432 22% on petrol | the bad tag: the plate |
| `--bad-soft-fg` | `#a33e21` | `#fc8b65` | orange #e54615 30% toward petrol / orange #fb6432 25% toward white | the bad tag: the text (AA at 11 px) |
| `--info-soft-bg` | `#bbdaed` | `#2a4a5d` | sky / sky 18% on petrol | the info tag (the internet): the plate |
| `--info-soft-fg` | `#0a2a3d` | `#ffffff` | petrol / white | the info tag: the text (AA at 11 px) |
| `--neutral-soft-bg` | `#e7eaec` | `#233f50` | petrol 10% on white / white 10% on petrol | the neutral tag (a label, the FM radio): the plate |
| `--neutral-soft-fg` | `#475f6e` | `#ced4d8` | petrol 75% on white / white 80% on petrol | the neutral tag: the text (AA at 11 px, on its plate and bare: the Dummy) |
| `--lora-soft-bg` | `#91c1b9` | `#284b58` | sage / sage 22% on petrol | the LoRa radio's tag: the plate |
| `--lora-soft-fg` | `#0a2a3d` | `#91c1b9` | petrol / sage | the LoRa radio's tag: the text (AA at 11 px) |
| `--hf-soft-bg` | `#0a2a3d` | `#a6d7d4` | the inverse pill: petrol / the inverse pill: mint | the Mercury radio's tag, the site's inverse pill: the plate |
| `--hf-soft-fg` | `#ffffff` | `#0a2a3d` | white / petrol | the Mercury radio's tag: the text (AA at 11 px) |
| `--waterfall-0` | `#000828` | `#000828` | as it was | the HF waterfall: the floor and its background (a rig's scale, the same in both themes: the picture is dark in the light theme too) |
| `--waterfall-1` | `#0834be` | `#0834be` | as it was | the HF waterfall: a weak signal |
| `--waterfall-2` | `#00aaff` | `#00aaff` | as it was | the HF waterfall: halfway up |
| `--waterfall-3` | `#ffe200` | `#ffe200` | as it was | the HF waterfall: a strong signal |
| `--waterfall-4` | `#ff2810` | `#ff2810` | as it was | the HF waterfall: the strongest |
| `--waterfall-rule` | `rgba(255, 255, 255, 0.45)` | `rgba(255, 255, 255, 0.45)` | as it was | the HF waterfall: the ticks of the frequency ruler |
| `--waterfall-ink` | `rgba(255, 255, 255, 0.92)` | `rgba(255, 255, 255, 0.92)` | as it was | the HF waterfall: the ruler's numbers, the times and the calls heard |
| `--waterfall-grid` | `rgba(255, 255, 255, 0.16)` | `rgba(255, 255, 255, 0.16)` | as it was | the HF waterfall: the curve's faint dB grid, the floor's line and the line of a quarter of a minute |
| `--waterfall-rx` | `#3ddc84` | `#3ddc84` | as it was | the HF waterfall: the band of a frame on the ruler while we listen |
| `--waterfall-tx` | `#ff5a47` | `#ff5a47` | as it was | the HF waterfall: the band on the ruler and the mark at the edge while we transmit |
| `--level-band` | `#e2f0e3` | `#1f3a24` | as it was | the receive level bar: its good range (an instrument's scale, as it was) |
| `--level-low` | `#5d6670` | `#98a2ab` | as it was | the level bar: too low |
| `--level-good` | `#2e7d32` | `#66bb6a` | as it was | the level bar: in the good range |
| `--level-high` | `#b26a00` | `#ffb74d` | as it was | the level bar: high |
| `--level-clip` | `#c62828` | `#ef5350` | as it was | the level bar: the sound card clips |
| `--scrim` | `rgba(10, 42, 61, 0.5)` | `rgba(0, 0, 0, 0.5)` | petrol 50% | the veil behind a dialog |
| `--map-label` | `#1d2125` | `#e3e6e8` | as it was | the map: text |
| `--map-halo` | `rgba(255, 255, 255, 0.9)` | `rgba(20, 23, 26, 0.9)` | as it was | the map: the halo of text |
| `--map-ring` | `#ffffff` | `#ffffff` | as it was | the map: the ring of a plain marker |
| `--map-mark` | `#1565c0` | `#6aa9ee` | as it was | the map: a plain marker |
| `--map-own` | `#1565c0` | `#6aa9ee` | as it was | the map: my station and my objects, their outline and their call |
| `--map-direct` | `#2e7d32` | `#66bb6a` | as it was | the map: the ring of a station heard direct |
| `--map-net` | `#5d6670` | `#98a2ab` | as it was | the map: the dotted outline of a station heard only over the internet |
| `--map-route` | `#1565c0` | `#6aa9ee` | as it was | the map: the route of the station picked |
| `--map-route-old` | `#5d6670` | `#98a2ab` | as it was | the map: the route of the packet before it |
| `--map-internet` | `#00697f` | `#4dc4de` | as it was | the map: a hop of the internet on a route |
| `--map-range` | `#1565c0` | `#6aa9ee` | as it was | the map: the circle of a digipeater's range |
| `--map-sign-bg` | `#ffd600` | `#ffd600` | as it was | the map: a signpost |
| `--map-sign-ink` | `#000000` | `#000000` | as it was | the map: the text of a signpost |
| `--map-select` | `#ff6d00` | `#ff6d00` | as it was | the map: the selected station and its track |
| `--map-select-wash` | `rgba(255, 109, 0, 0.18)` | `rgba(255, 109, 0, 0.18)` | as it was | the map: the wash of the selected station |
| `--map-plate` | `rgba(255, 255, 255, 0.88)` | `rgba(255, 255, 255, 0.88)` | as it was | the map: the plate under a symbol in the dark theme |
| `--map-track` | `#2f80ed` | `#2f80ed` | as it was | the map: a track |
| `--map-layer` | `#8e24aa` | `#ce93d8` | the map's own | the map: an aircraft or a ship, and its mark in the Layers box |
| `--map-twilight` | `rgba(11, 26, 58, 0.1)` | `rgba(0, 0, 0, 0.25)` | the map's own | the map: the shade where the sun is down |
| `--map-night` | `rgba(11, 26, 58, 0.14)` | `rgba(0, 0, 0, 0.4)` | the map's own | the map: the shade added where the sun is more than 6° down |
| `--map-control-ink` | `#333333` | `#333333` | the map engine's own | the map: the drawing on its buttons, white in both themes (the Layers button's as the zoom buttons') |
| `--wx-temp` | `#d84315` | `#ff8a65` | as it was | the weather graphs: temperature |
| `--wx-pressure` | `#7b1fa2` | `#ce93d8` | as it was | the weather graphs: pressure |
| `--wx-wind` | `#00838f` | `#4dd0e1` | as it was | the weather graphs: wind |
| `--wx-rain` | `#1565c0` | `#64b5f6` | as it was | the weather graphs: rain |
| `--speed` | `#2e7d32` | `#81c784` | as it was | the speed graph of a moving station's card |
| `--signal` | `#ad1457` | `#f48fb1` | as it was | the signal graph of a station's card |
| `--code-field` | `#ffffff` | `#ffffff` | white | the phone code in Settings, Web page: its field, white in both themes, for every camera |
| `--code-dark` | `#0a2a3d` | `#0a2a3d` | petrol | the phone code: its dark modules, the same in both themes |

## The icon

The icon (`ui/public/icons/icon.svg`, the same text as `site/favicon.svg` and the loading page's mark; every raster file drawn from it by `scripts/make-icon.py`) is the palette's too: the tile and the pin's hole petrol `#0a2a3d`, the pin and the inner waves white, the outer waves mint `#a6d7d4`. `tests/test_icon.py` holds the files to these colours.

## The shapes and the fonts

The corners are three tokens, the site's: `--radius` for a control, `--radius-box` for a group, a card, a menu or a bubble, `--radius-pill` for the tag; a corner written anywhere else is one of them, `0` or `50%` (a circle), and `ui/src/styles/radii.test.ts` fails for any other (the receive level bar, `HfLevelBar.vue` `5px`, and the scope, `HfScope.vue` `4px`, are instruments and keep theirs). The tail corner of a message bubble is `0`. The sizes are the page's own: 14 px text, the tag's size, the fieldset with its legend, all spacing, the 2-px focus ring.

| token | light | dark | recipe | for |
|---|---|---|---|---|
| `--shadow` | `0 2px 8px rgba(10, 42, 61, 0.12)` | `0 2px 8px rgba(0, 0, 0, 0.5)` | the site's: petrol 12% / the site's | the shadow of what stands over the page: a card, a menu, the toast |
| `--radius` | `4px` | `4px` | the site's | the corner of a control: a button, an input, a small box in a line |
| `--radius-box` | `6px` | `6px` | the site's | the corner of a group, a card, a menu, a dialog, a bubble |
| `--radius-pill` | `999px` | `999px` | the site's tag | the round ends of the tag and of a grip |
| `--control-h` | `32px` | `32px` | the page's own | the height of every text button, input and select of a form or a toolbar |
| `--control-h-small` | `24px` | `24px` | the page's own | the compact button inside a list row, a bubble or a line of text |
| `--action-w` | `11em` | `11em` | the page's own | the least width of the button that is the action of a row |
| `--font` | `system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", "Noto Sans", Ubuntu, Cantarell, sans-serif` | `system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", "Noto Sans", Ubuntu, Cantarell, sans-serif` | the site's | the page's text: the site's stack |
| `--mono` | `ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace` | `ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace` | the page's own | figures, calls and packets: the page's own stack (every column of figures is measured in it) |
