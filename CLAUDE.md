# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A toolchain (Python scripts + generated static HTML) for DJI drone board repair. It reads
proprietary boardview files, aligns board photos to them, exports netlists / measurement
sheets / net-search pages, and generates a local **HUB.html** that ties everything together
and launches OpenBoardView. Not a git repo, no package manager, no tests — scripts are run
individually or in batch from `atualizar.bat`. Comments and UI strings are in Portuguese; keep
that convention.

## Environment

Paths are resolved at runtime by `paths.py` — never hardcode them again. `BV` is the repo
root (from `__file__`); `DRONES` (the data root, outside the repo) is auto-detected, and
`BOARDVIEW_DRONES` overrides it. `python paths.py` prints both; `python paths.py --drones` is
what the `.bat` files call. The `.bat` files get their interpreter from `py.bat`, which probes
known locations and then `where python`.

Currently: repo `C:/Users/usuario/Documents/Boardview`, data `C:/Users/usuario/Pictures/Drones/Drones`,
Python 3.12 at `%LOCALAPPDATA%\Programs\Python\Python312`.

Dependencies: `numpy`, `Pillow`, `pycryptodome` (imported as `Crypto`), plus stdlib
`sqlite3`/`zipfile`/`http.server`.

## Which viewer matters

**`digital_viewer/` is the viewer in use** — it is the fastest and the nicest of the three, and
new work goes there. `viewer.html`, `board_viewer.html` and the patched OpenBoardView still
work and their pipelines are intact, but they are not the focus.

## Data model

The **data root** (`DRONES`) is one folder per drone model (`DJI Mini3 Pro`, `DJI Mavic Air2`, …),
each containing that model's `.pcb` boardviews, the reference `.pdf`, the aligned `_bg.png` photo,
and the `.conf` OpenBoardView writes next to each `.pcb`. It lives outside this repo on purpose —
`servidor.py` maps it to the URL prefix `/_drones/` rather than symlinking it into a synced folder.
Files starting with `._` are macOS resource forks and are skipped everywhere.

The **repo** holds only derived artifacts, one file per board, named after the `.pcb` basename:
`Netlists/`, `Cadernos/` (measurement sheets), `Malhas/` + `Malhas-templates/` (net search),
`boards/*.js` (local viewer data), `viewer_data/`, `thumbs/`, `digital_viewer/build/`.
`DigitalBoard/` is a scraped mirror of a third-party site (`.bvr` boardviews, PDFs, JSON voltage
maps), catalogued in `DigitalBoard/_INDICE.md`.

## The XZZPCB `.pcb` format

`xzz_parts.py` is the shared parser — **import `load_parts()` from it rather than re-implementing**.
Format essentials, replicated from OpenBoardView's `XZZPCBFile.cpp`:

- Everything before the `v6v6555v6v6` marker is XOR'd with the byte at offset `0x10`.
- `u32@0x20 + 0x20` = main block start, `u32@0x28 + 0x20` = net block start; each block begins
  with its own size.
- Component blocks are type `0x07` and are additionally **DES-ECB encrypted** with key
  `DCFC12AC00000000`. Pin sub-blocks are type `0x09`; coordinates are in units of 1/10000.
- Outline segments live on layer 28 (block types `0x05`/`0x01`), also scale 10000, translated so
  min → (0,0). That translation defines the coordinate frame everything else (photos, viewer JSON,
  annotations) is expressed in.

`xzz_layout.py <pcb>` dumps offsets/blocks and is the first thing to run when a file won't parse.
`rename_nets.py` is the only script that writes back into a `.pcb` (rewrites the net name block
in place, preserving indices); it is dry-run unless given `--apply` and backs up to `.pcb.bak`.

## Photo alignment (the non-obvious part)

`align_bg.py` maps a board photo onto the `.pcb` outline so OpenBoardView can show it as a
background image. It does **not** do a global fit: it splits the outline into islands (union-find
over connected segments) and the photo into blobs (threshold vs background colour), and when the
counts match it stretches each blob onto its island's bbox, producing offset 0 and uniform scale.
Only when counts disagree does it fall back to a global bbox-union mapping — that fallback is a
warning sign, not a success. The result is written as `Top/BottomImage*` keys into the `.conf`
next to the `.pcb`.

- `batch_bg.py <DRONES> [--apply]` runs this over everything; classes A/B/C in its header describe
  the blob-to-island cases. Dry-run without `--apply`.
- `auto_orient.py`, `verify_bg.py` — decide/inspect flips and rotations. `verify_bg` renders pads
  over the photo and is the way to confirm an alignment before trusting it.
- `align_bvr.py` does the same against DigitalBoard `.bvr` files, which carry full pads and nets.
  Its `compor()` is the reusable entry point (the CLI just wraps it); `secoes_validas()` is the
  single source of truth for how a board splits into sections — a stray outline fragment holding
  under 5% of the pins is discarded, otherwise the ppu average blows up and the composite comes
  out tens of thousands of pixels wide. **When that guard fires, it retries on the other axis
  before giving up.** `valley_split` keeps the *widest* valley of either axis, and on `mini1` that
  was a spurious one in X yielding a 2.3%-of-pins island; the old code discarded the split and left
  the whole board as one section, where no single transform could align it (+4.9). The good valley
  was in Y all along — splitting there gives +28.6 and +48.5. Only `mini1` is affected, but the
  failure mode is general: a degenerate split on the best axis is not evidence that the board is
  undivided.
- **A valley must clear 5% of the peak — and when nothing does, the 15% split is a *candidate*,
  not a decision.** `mavic3pro`'s seam holds 39 pins against a 35.7 threshold: it missed by three
  and the whole board became one section. Loosening the threshold for everyone fixes it and breaks
  others, so `valley_split` takes a `frac` (env `BOARDVIEW_VALE_FRACS` overrides, for measuring),
  `ilhas_e_pinos` returns **both** segmentations when they differ, and `processar` scores them the
  same way it scores rotation and mirror. Measured, whole vs split: `air2s` 15.5 → 35.4/24.6 and
  `mavic3pro` 30.5 → 52.3/0.9, but `air3` 23.8 → 7.7/5.1 and `rc-plus` 7.3 → 1.9/1.6. Splitting
  everything would have wrecked the last two. Boards that already split have one candidate, so
  they cost nothing extra and cannot change.
- **After the choice, `<id>_secoes.json` is the only source of truth for the sections.** The env
  default is the strict `0.05`; only `foto_viewer.ilhas_e_pinos` asks for the loose candidate. It
  briefly defaulted to `0.05,0.15`, and then `qc_align`/`refine_align`/`medir_afim`/`medir_giro`
  — which used to recompute the split themselves — split air3 and rc-plus while their photos were
  whole: the QC drew half a board stretched over the full photo. Recomputing with *any* default is
  wrong for some board, because the split is chosen per board. So `qc_align.ilhas_e_pinos` (which
  the other three call) now reads each section's `box` from the manifest and only recomputes when
  there is no manifest. QC for mavic3pro reads 52.2/0.9, matching `foto_viewer`.
- **The score is a pin-weighted mean, not a sum.** A sum favours splitting purely by having more
  terms. Weighting by pins puts one and two sections on one scale without reordering anything
  within a given section count.
- **`SECOES_FORCADAS` overrides that score per board, and `mavic3pro` is in it.** Contrast averages
  over the board and cannot see that one perfect half plus one hand-adjustable half beats a
  uniformly mediocre fit: by the mean, whole (30.5) beats split (24.6 weighted), yet the split's s0
  is +52.3 and the bench asked for it. That is a human call, recorded as one — not the measurement.
  `dji-mavic3-pp002022-10-pcb-layer` is the same dilemma at 23.6 vs 24.1 and is **not** forced.

### One image per half — the layout of these boards

**These `.bvr` files have no bottom side: every pin is `PIN_SIDE T`.** The board's two faces are
laid out as two **islands** of one outline (`secoes_validas` finds them), so the viewer's
TOP/BOTTOM buttons separate nothing, and "which side am I on" has to come from *where the cursor
is*, not from `displayMode`. Some boards are a single island — and there the photo still shows two
faces, so only one of its blobs belongs on that outline; taking the union of both squeezes two
faces onto one board (that was the `rc-plus` failure: a 9208x3168 outline filled with a 2:1
squashed photo).

The XZZ photo has no fixed layout either: the front face may be on the left, on the right, or
stacked. So the pairing between photo blobs and outline islands is a real unknown — and a wrong
pairing is not fixable by any amount of mirroring or scaling.

`foto_viewer.py` therefore emits **one JPEG per half** — `build/FOTO/<id>_s0.jpg`, `_s1.jpg` — plus
`<id>_secoes.json` giving each half's island box in `.bvr` units. Each half then carries its own
scale, offset and mirror. That is what fixes "aligning the bottom throws the top off": the two
halves no longer share one transform.

For each board it searches **all four rotations** × blob-to-island assignment (including swapped)
× mirror (none/H/V/HV). Do not "optimise" 180/270 away by arguing they equal 0/90 plus the HV
mirror: that is true of the pixels but **not of the blob detection**, which runs on the already
rotated image, so the crop position and margins come out different. Dropping them regressed
`mini3` from +32/+48 to +12/+23 — its best configuration was rot=180.
and scores every candidate with **the same measure used to judge the result**, at the same
resolution. A cheap shift-only triage was tried first and thrown out: it kept picking
configurations the final measure contradicted, and scoring at 700px while judging at 2000px is
incoherent on its own terms — the contrast is not scale-invariant, so the ranking changes. It costs
~4 minutes a board; that is the price of the selection and the verdict agreeing.

### Getting a half onto its pads exactly

`refine_align.py` supplies the measurement, and it uses **two different signals — don't mix them
up**:

**Scale and translation — FFT cross-correlation.** Pads read as bright blobs against the
substrate, so a local-mean high-pass of the photo correlates strongly with a mask of the island's
`PIN_ORIGIN` points; the peak *is* the residual error. `medir_secao_px` searches X/Y scale plus
translation coarse-to-fine (700px → 1400px → full). Convergence is the test: re-measuring a
corrected half must report scale ≈ 1.0000 and displacement (0,0).

**Mirror — pad contrast, and only after refining.** Correlation **cannot** decide this: measured
across this collection, the correct and the mirrored half score within a few percent of each other
on peak height, on peak prominence, and on coarse contrast alike — a dense pin cloud over a board
that is copper nearly everywhere correlates about as well either way. What separates them is
`contraste` (pixel under the pin vs. its surroundings) at full resolution *after* a refinement
pass. Note this number is **only comparable within one half, at identical framing**: a well-aligned
board can score +1 and another equally good one +25, depending on how bright its pads are, and a
*tighter crop of the same half* scores higher merely because it magnifies the pads. Never rank
boards by it, and never use it to choose between crops — that confound cost real time here.
`mavic3pro` scored +1.33 while being visually perfect.

**The whole correction is one affine — scale, translation, rotation AND shear.**
`medir_afim.py` divides a half into a grid, measures each block's own shift, and least-squares-fits
a full 2x2 matrix plus translation to that field. Shear is not optional: photographed slightly off
axis, a pad row that is perfectly horizontal in the boardview comes out sloped, and aligning one
end lifts the other. Worse, **a rotation-only fit absorbs shear into a near-zero rotation** — it
reported 0.00° on a half that had +0.27° rotation and +0.35° shear, so the defect was invisible in
the numbers while obvious on screen.

Rules learned the hard way here:

- **Compose, then resample once.** The scale/shift stage and the affine stage are multiplied into a
  single matrix and applied straight to the source crop (`avaliar_afim`). Every extra resampling
  blurs the pads — rotating the finished JPEG once dropped contrast 5.5 → 2.1, where the same
  rotation at source raised it to 17.8.
- **Guard the correction, but calibrate the guard.** The measurement can fail (small board, few
  blocks, weak correlation) and then the affine makes things worse — one board went +24 → +7. So
  the affine is kept only if contrast does not drop by more than 20%. A stricter guard (`any` drop
  rejects) was wrong: it discarded a good affine over 7.9 vs 7.3, which is noise, and left 0.52° of
  shear in place.
- **The grid adapts.** A fixed 4x4 with 40 pins per block left small boards (343 pins in a half)
  with no affine at all; it now falls back to 3x3 and 2x2.
- **Residual is the cross-board measure, contrast is not.** What `medir_afim` calls `residuo` is
  what remains after fitting the affine — if it is large (4-6px on two halves here), the distortion
  is *not* affine (lens, or pieces individually displaced) and no 2x2 matrix will fix it.

**Rotation alone — the earlier, superseded approach.** `medir_giro.py` still exists and is useful
for a quick look, but do not use it to decide anything: see the shear-absorption trap above.
Historical note on its sign: The refine above finds
the *average* shift, so a photo rotated half a degree sails through it and the board sits visibly
crooked. `medir_giro.py` divides a half into a 4x4 board, measures each block's own shift, and
least-squares-fits a rotation to that field (`dx = s*px - t*py`, `dy = t*px + s*py`). Apply the
measured angle as-is — the sign does **not** depend on the mirror variant, verified across three
halves with different variants. **Rotate at source resolution**, inside `metade()` before the
resize: rotating the finished JPEG costs a second resampling that blurs the pads and measurably
*lowered* contrast (5.5 → 2.1), where rotating at source *raised* it (5.5 → 17.8). Angles here run
from 0.02° (already straight) to 0.56°; the fix took `mini4pro` s1 from +22.9 to +57.5.

`qc_align.py` draws the pins over each half into `qc/<id>_qc.jpg` (halves side by side) and prints
the per-half contrast. When in doubt, look at the image — it is the only real arbiter.

### Viewer gotchas that look like broken features

- **The board id is computed in `index.html`'s `preload` and published as `window.__board`;**
  `inicio.js` reads that. They used to derive it independently, and when a browser held one of
  the two files in cache they disagreed — the `.bvr` loaded for one board and the photo was
  fetched for another, so the photo silently vanished. Both script tags now carry `?v=`; bump it
  together with the asset `v` in `preload` whenever you touch them.
- **The default board (no `?board=`) must be an id that exists in `build/DRONE`.** It was a stale
  `dji-mini2-pp001950-03-pcb-layer`; `loadStrings` 404'd, `parseFile()` threw, `setup()` died
  before registering anything, and the keyboard controls were dead with no error on screen. There
  is now a fallback that redirects to the first entry of `boards.json`, `parseFile()` is wrapped,
  and `ajusteIniciar()` runs first so the controls exist even when a board fails to load.
- **A native `<select>` will not open if its events reach p5.** p5 listens for the mouse on the
  *window*, and this viewer's `mousePressed()` ends in `return false`, which p5 turns into
  `preventDefault()` — and `preventDefault` on a mousedown stops a select from opening. Every
  dropdown added to the toolbar was born dead until `protegerControles()` started stopping
  propagation inside `#controls`, `#componentInfo` and `#componentModal`. **Any new control must
  sit inside one of those containers**, or repeat the guard. The redesign added a top bar and a
  panel handle outside all three, so `skin.js` repeats the guard for `#topbar` and `#btnPainel`.
- **The guard must not swallow `mouseup`** — and it used to. Only `preventDefault` on *mousedown*
  breaks a `<select>`; `mouseup` was in the list for symmetry, and that was the bug. p5 sets
  `mouseIsPressed = true` when a mousedown reaches a button registered through
  `select('#id').mousePressed(...)`, and with the matching mouseup stopped it never went back to
  false: after clicking TOP or BOTTOM the view panned by itself under a released mouse, and a drag
  that *ended* over the bar stayed stuck the same way. Invisible while the bar lived in a corner at
  the top; obvious once the redesign put the dock over the board. Stop `pointerdown`, `mousedown`,
  `click`, `dblclick` and `wheel` — never `mouseup`. (The original code carried a one-off
  `stopPropagation` on the search input alone — someone hit this before and patched only their own
  symptom.) Verify by mechanism, not by looks: a click on the bar must *not* reach the window
  listener, while a click on the canvas must still arrive with `defaultPrevented: true`.
- **A duplicated `id` kills a feature in silence.** `componentList` was on both the search
  `<datalist>` and a div inside the modal; `select('#componentList')` picked the div, so the search
  dropdown was permanently empty — 0 options, now 2179. The modal's div is `listaDaMalha` now.
- **Setting a control's value from JS proves nothing** — that path bypasses exactly what was broken
  above. Click it.
- **`servidor.py` serves a whitelist, so a new folder 404s until you add it.** It used to serve
  any file on the disk (`/C:/Windows/win.ini`, `..%2F`). Now `resolver()` only allows `HUB.html`,
  `viewer.html`, the `PASTAS` prefixes (thumbs, boards, Malhas, Cadernos, Netlists, PDFs-Drone,
  DigitalBoard/pdf, digital_viewer/assets and /build) and top-level `.html`/`.js` of
  `digital_viewer/` minus `mine2_db.html`, then confirms with `realpath` + `commonpath`. No
  directory listing except `PDFs-Drone`. Requests must carry a known `Host` (add the company
  server's name to `BOARDVIEW_HOSTS`). `POST /ajuste/<placa>` needs JSON, same Origin, an existing
  board, and passes `validar_ajuste()`, which also drops other boards' keys. If the HUB or the
  viewer starts loading from a new folder, add it to `PASTAS` — otherwise it fails as a silent
  404. Remaining low-priority items are listed in `PLATAFORMA.md`.
- **The bench notebook (`medicoes.js` + `medicoes_db.py`, phase 1 of `PLATAFORMA.md`) must never
  lose or duplicate a reading.** Every V/Shift+V and D/Shift+D also calls `cadernoRegistrar()`,
  which pushes an event into `localStorage['caderno_fila']` *first*, then `POST /api/leituras`.
  An event leaves the queue only after the server answers, and the server answers only after the
  SQLite commit (WAL, `synchronous=FULL`) plus the day's JSONL mirror in `dados/`. The uuid is
  made in the browser, so a resend is `INSERT OR IGNORE`. Rows are append-only: deleting a value
  writes an `evento='retira'` row. The key of a reading is `fp` (sha256 of the `.bvr`'s sorted
  `PART|PIN|NET` lines) + the RAW net (`pin.netOriginal`, never the alias) — NC pins become
  `PART.PIN_NUMBER`. Without Shift = `papel='reparo'` (board on the bench); with Shift =
  `papel='ref'` (known-good board, the only kind that will vote in phase 2, and only with an OS).
  `dados/` sits outside the served whitelist; `BOARDVIEW_DADOS` points it elsewhere for tests.
- **Phase 2: one `servidor.py`, two roles, and `consenso.py` is the only place of the voting
  rule.** With a URL in `central.txt` (or `BOARDVIEW_CENTRAL`) the server is a *bench*: a thread
  pushes local rows to the central's `POST /api/leituras` in `seq` order and advances the `sync`
  table pointer only when the central answered the whole batch (accepted + rejected count must
  match); `/api/consenso` proxies the central and falls back to `dados/consenso/<placa>.json`.
  Without it the server is the *central* (or standalone) and computes consensus from its own DB.
  Never ship `central.txt` to the server — `empacotar_central.py` leaves it and `dados/` out, and
  `servidor-central/instalar.sh` refuses to run if it is there. The viewer only *displays*
  consensus (`consensoLinhas()` in `medicoes.js`); the tolerance it uses to flag "this board is
  off" comes from the server response, not from a copy in JS. The server is threaded now
  (`daemon_threads`, handler `timeout = 15`): anything that writes a file must use a unique temp
  name or `_trava_ajuste`. On Linux paths are case-sensitive — links that work on Windows can 404
  there; all current links were checked. Deployment: `servidor-central/LEIAME.md`.
- **Anything from data goes through `escHTML()` before `innerHTML`; everything else uses
  `textContent`.** Names come from the `.bvr` and from people renaming; measurements are typed.
  p5's `createElement(tag, content)` sets `innerHTML`, so the search datalist is built with the
  DOM API instead.
- Nets span both halves — about 37-39% of them in the boards measured. Following a trace to the
  other face is already covered by net selection and the PRÓXIMO button (also bound to Enter).

### The redesign (`digital_viewer/skin.js`)

The interface follows `Viewer redesign Galv/Viewer Galvao.dc.html` (Claude Design). The port rule
was **appearance only**: `index.html` was rewritten, the engine was not. Three consequences worth
knowing before touching it:

- **`skin.js` polls the state every 250 ms instead of listening to clicks.** Half the actions come
  from the keyboard (`F`, `A`, `T`, arrows) and never pass through a button, so click listeners
  would leave the highlighted buttons lying whenever someone used a shortcut — which is the normal
  way to use this at the bench. Reading four globals four times a second costs nothing.
- **`rotular(el, txt)` replaces `el.innerHTML = 'emoji<br>TEXT'`.** The buttons now carry an inline
  `<svg>`, and writing `innerHTML` would erase it. The text lives in a `<span data-rot>`; with no
  such span `rotular` falls back to `innerHTML`, so the modules still work in an older `index.html`
  (`nucleo.js` defines a fallback copy for the same reason).
- **Modules reuse the buttons instead of creating them.** `ajusteIniciar`, `botaoFaceUnica` and
  `botaoHub` look for their id first and only build one when it is missing. The two `<select>`s are
  still created in `#controls` by JS; `skin.js` moves them to the top bar and strips their inline
  style.

Fonts and assets are local (`digital_viewer/assets/`): the Google Fonts link is gone, Orbitron was
replaced by RaceSport. The bench may have no internet.

**Never load an optional file with a p5 loader inside `preload()`.** In the bundled p5 1.6.0,
`loadJSON`/`loadStrings` call the error callback but never decrement the preload counter, so a
missing or malformed file leaves every board on "Loading..." with no error (only `loadImage`
releases on failure). `build/malhas.json` is hand-edited, and loading it in `preload` meant one
stray comma froze the viewer for all boards. It now comes from a plain `fetch` started in
`index.html` (`window.__malhasP`, missing/invalid → `{}`), and `setup()` calls
`reaplicarApelidos()` when it resolves. The `.bvr` `loadStrings` still has this flaw: a 404 on a
board that is also first in `boards.json` hangs the same way.

### Manual alignment in the viewer (`digital_viewer/ajuste_fundo.js`)

The automatic pass gets most halves right; this is the escape hatch for the rest, and the only
way to fix a swapped pairing. **Every command acts on the half the mouse is over** (`ajusteApontar`
→ `secaoNoPonto`), because there is no top/bottom to key off:

| | |
|---|---|
| Ctrl + drag | move that half |
| Ctrl + wheel | scale it (Ctrl+Shift = X only, Ctrl+Alt = Y only) |
| H / J | mirror horizontally / vertically |
| T | swap the two halves |
| C | cross-side cursor: marks the same physical point on the other face |
| S | type the scale (X Y) — for gross errors the wheel would take forever to walk |
| arrows | nudge 1 screen px (Shift = 10) |
| R / E | reset that half / download `ajustes.json` |

The cross-side cursor mirrors across the split axis (side-by-side halves mirror in X, stacked
ones in Y) — measured, not assumed: overlaying the two islands' outlines, the mirrored fit wins in
5 of 6 boards. It lands **close, not exact**: the two islands' bboxes differ 1-4% in aspect, which
is why the marker is a circle rather than a point. The right physical spot is inside it.

No right-click binding: the browser claims that event, so it is unusable here. Modifier keys are
ignored by the key handler for the same reason (`Ctrl+R` must stay reload).

Arrows convert a screen step through `screenToWorld` rather than adding to world x/y, because the
viewer starts rotated 180° and horizontally flipped — a raw `+x` would send the photo left.
Halves are drawn inside `scale(1,-1)`, so a half's image top edge goes at local `-box[3]`; adding
the outline bbox offset there double-counts and parks the photo off-screen.

Adjustments live in `localStorage` keyed `"<board>|<half index>"`, and `E` exports the non-zero
ones as `ajustes.json`; drop that file in `digital_viewer/build/` and it becomes the default for
any browser, with `localStorage` still taking precedence. A manual adjustment survives a
regeneration of the JPEGs — so if the new render is already aligned, the old adjustment now skews
it: reset with R.

### Other viewer features and where their data comes from

| feature | file | state lives in |
|---|---|---|
| single-face fold (F) | `face_unica.js` | derived at runtime from `_secoes.json` boxes |
| cross-side cursor (C) | `ajuste_fundo.js` | — |
| photo adjust per half | `ajuste_fundo.js` | `localStorage`, exportable to `build/ajustes.json` |
| rename components (N) | `renomear.js` | `localStorage`, exportable to `build/nomes.json` |
| measured voltages (V) | `tensao.js` | `localStorage` per board+net |
| model menu, HUB button | `menu_modelo.js` | `build/modelos.json` (`gen_modelos.py`) |

Every one of these follows the same pattern: `localStorage` is the working copy, and a JSON dropped
into `build/` is the shared default that any browser picks up, with `localStorage` winning. Keep
new state on that pattern rather than inventing a third one.

`face_unica.js` does **not** re-derive the island split; it reads the boxes out of
`_secoes.json`, which Python computed. An earlier attempt to find the split in JS from the largest
outline gap picked a thin strip instead of the real division. Renaming keeps the factory name in
`part.nomeOriginal` and shows it in parentheses — the netlist, cadernos and schematics all use the
factory name, so losing it would break the cross-reference.

## Two viewers, two pipelines

1. **OpenBoardView** (`OpenBoardView/openboardview-10.0.0-patched/openboardview.exe`) — the real
   app. `patch-obv-tensoes.diff` adds a "Tensoes" checkbox that colours pins by voltage read from
   the annotations table. Annotations go into `<base>_pcb.sqlite3` via `annotate.py` (from a
   curated CSV) or `json_to_annotations.py` (from DigitalBoard JSON `diodeReading` values, matched
   to the `.pcb` by median dx/dy over shared component names). HUB links open boards through the
   `obvboard://` protocol, handled by `obv-launch.vbs`.
2. **Browser viewers** — `viewer.html` (reads `boards/<base>.js`, `?board=` or `?model=` using
   `boards/_models.js`), `board_viewer.html`/`viewer_data/`, and `digital_viewer/` (p5.js, renders
   `.bvr` + photo from `digital_viewer/build/`).

## Running it

```bash
python servidor.py            # serves the repo on 127.0.0.1:8777, /_drones/ -> data root
python servidor.py 8788       # another port, to test without touching a running instance
```
On Windows a second `servidor.py` can bind 8777 even though one is already there (`SO_REUSEADDR`),
and then requests are answered by whichever socket wins — which looks exactly like edits to
`index.html`/the viewer `.js` files having no effect. If served content is stale, close every server window
before starting a new one, or use a different port.
Then `http://127.0.0.1:8777/digital_viewer/index.html` (or `/HUB.html`). `Viewer DigitalBoard.bat`
and `Viewer.bat` do both steps. The viewer must be served over HTTP — opening `index.html` from
disk breaks its `fetch` of `boards.json`.

```bash
python foto_viewer.py                  # todas as placas: compoe + refina + QC + boards.json
python foto_viewer.py mini3pro         # so as que casarem com esse trecho de nome
python refine_align.py mini3pro        # so medir o residual de uma foto ja pronta
python qc_align.py                     # conferencia: qc/*_qc.jpg + nota de contraste
```
A full `foto_viewer.py` run takes ~45 s per board. After regenerating photos, bump the `v=`
cache-buster in `digital_viewer/index.html` `preload()` or the browser serves the old JPEGs.

`atualizar.bat` is the full regeneration pipeline and the canonical order of operations:
backgrounds → netlists → cadernos → malhas → `boards/*.js` → merged `.brd` per model + merged
background → refs/models index/thumbs → `gen_hub.py`. Most steps are per-`.pcb` loops, so to
rebuild one board just run that step's script on the single file. `gen_hub.py` must run last;
it only emits a link/badge for an artifact that already exists on disk, so a missing button in
HUB.html means the upstream step failed silently (the loops in `atualizar.bat` redirect to `nul`).

`merge_boards.py` / `gen_merged_all.py` write the open ASCII `.brd` format so several boards of
one model open side by side; net names are prefixed per board tag so malhas don't merge.
`render_brd.py` reimplements OBV's `DrawOutlinePoints` to preview what OBV will actually show —
use it when a merged outline looks wrong before opening the app.

## Shared state that is NOT in `build/` (added Nov 2026)

The "localStorage + JSON in `build/`" pattern above is for per-PC conveniences. State that the
team creates and that must survive a program update lives under `dados/` (outside the served tree,
never shipped by `empacotar_central.py`) and goes through the server:

| what | module | file | API |
|---|---|---|---|
| readings (voltage/diode) | `medicoes_db.py` | `dados/medicoes.sqlite3` | `/api/leituras`, `/api/consenso` |
| classification, part names, net nicknames, suggestions (mode Q) | `anotacoes.py` | `dados/anotacoes/<placa>.json` | `/api/anotacoes/<placa>` |

`anotacoes.py` only stores and validates; the bench↔central network part is in `servidor.py`
(`anotacoes_da_placa`, `sincronizar_anotacoes`). Things that were wrong once and must not come back:

- **`digital_viewer/build/anotacoes/` is only a seed.** It is copied once into `dados/anotacoes/`
  when a board has no file there. Writing shared state into `build/` meant every package update
  of the central overwrote everyone's marks, and test servers polluted the real file.
- **First contact with the central** (`ANOT.primeiro_contato`, called from `_do_central`): marks
  made on a PC before it had a `central.txt` never went through the queue, and the bench used to
  replace its local file with the central's copy — losing them. Now, once per board (marker
  `dados/anotacoes/.central-<placa>`) and only after the central has answered, the bench queues what
  the central does **not** have; for a part classified on both sides the later `em` wins; names and
  nicknames that already exist on the central are left alone. Queuing everything was also wrong: a
  PC installed with an old seed would overwrite newer corrections.
- **The package seed is today's `dados/anotacoes`**, written into the tarball as
  `digital_viewer/build/anotacoes/<placa>.json` by `empacotar_central.py`; the on-disk
  `build/anotacoes` folder is frozen history and is skipped.
- **One invalid change must not block the rest.** `POST /api/anotacoes` judges each change alone and
  answers `{gravadas, recusadas}`; the browser and the bench drop/record the refused ones
  (`dados/anotacoes/recusadas-<placa>.json`). A whole-batch 400 made both queues retry forever when
  two PCs ran different versions of the program.
- **Net identity** (`malhaCanon` in `tensao.js`, `canon` in `bvr.py`): some `.bvr`
  files name nets with a voltage prefix (`7P0_Net9`, `3P0Net18`, `VCC_3P2V_Net65`) while
  `malhas.json`, the annotations and `.cobre.json` use `Net9`. Always look a net up by the raw name
  and then by the canonical one. The trailing `Net<n>` is unique on every board.

Tests: `python -m unittest discover testes -v`. They set `BOARDVIEW_DADOS` to a temp dir before
importing anything and start their own servers on ports 8791/8792 — never the real `dados/`. When
testing by hand, start the server with `BOARDVIEW_DADOS=<temp dir> python servidor.py 8797`.

Scripts around mode Q: `sugerir_placas.py` (topology suggestions for every board),
`exportar_placa.py <placa>` (one JSON with parts, names, types, nets, nicknames and readings, for
external tools), `foto_viewer.py` (`SECOES_FORCADAS`, `CORTE_FORCADO` for boards whose automatic
split is wrong).

## Layout of the code after the Nov 2026 cleanup

`SCRIPT3.js` (the p5 engine, 1,750 lines) was cut into ten files at whole-line boundaries, no code
changed. They are classic scripts sharing one global scope, loaded by `index.html` in this order
— the order matters because some of them run code at load time:

| file | what is in it |
|---|---|
| `nucleo.js` | global state (`parts`, view, selection), `escHTML`, `tensaoValida` |
| `tensao.js` | `boardKey`, `malhaCanon`, `apelidoMalha`, measured voltage per net (`setNetVoltage`) |
| `inicio.js` | `setup()`, board picker, starts every module |
| `desenho.js` | `draw()` |
| `vista.js` | screen↔world conversion, `mouseWheel` (zoom and photo scale) |
| `clique.js` | `mousePressed`/`Dragged`/`Released`, tooltip |
| `painel.js` | `tensaoDoPino`, `netNameToVoltage`, `updateComponentInfo`, net component list, modal |
| `pecas.js` | `renderBuffer`, net lines, component boxes and names |
| `bvr.js` | `parseFile()` — the browser's `.bvr` reader |
| `busca.js` | search, next pin in net, `windowResized`, `keyPressed` |

The feature modules (`skin`, `renomear`, `diodo`, `medicoes`, `cobre`, `classificar`,
`menu_modelo`, `face_unica`, `ajuste_fundo`) load before these. `servidor.py` only serves `.js`
files directly inside `digital_viewer/` — a `js/` subfolder would 404.

Python side: `bvr.py` is the one `.bvr` reader for scripts (`pecas()`, `canon()`); only
`align_bvr.parse_bvr` (outline segments, photo pipeline) stays separate. `anotacoes.py` is the
annotation store. Unused scripts and the old HTML viewers were archived into
`arquivo-morto-2026-11-16.zip` (not in git; the code is also in the first commit).

The repo is under git since 2026-11-16 with **code only**: board data (`digital_viewer/build`,
`boards`, PDFs…) and `dados/` are ignored on purpose — third-party material and team state must not
reach a public remote. `medicoes_db.py backup` (the central's daily timer) now also writes
`anotacoes-<stamp>.zip` next to the database copy.
