# Gallery Ledger: notes for whoever edits this next

Read this first. It records what the app is, how it is built, the rules we agreed on, and what was deliberately removed so it is not rebuilt by accident.

## What it is
A personal art catalogue for one person on an iPhone, installed from https://cadernaders.github.io/Gallery-Ledger/ (GitHub Pages, branch `main`). The owner is not a programmer: explain in plain words, show things only when they matter, keep the interface quiet and symmetrical, avoid big speculative redesigns, and keep screens consistent with each other.

## Files
- `index.html`: the whole app (HTML, CSS, JS in one file, no build step). Photos are in the phone's IndexedDB; works are in localStorage (`gallery-ledger-paintings`).
- `sw.js`: service worker. Network-first for same-origin GETs, and serves stored photos at `_blob/<id>`.
- `manifest.webmanifest` and the `icon-*.png` files: the installed-app bits.
- `data/paintings.json` and `data/paintings.bin`: the photo-recognition index (5030 works; one int8 vector of 512 numbers per work). Built by `tools/build_index.py` through the GitHub Action `.github/workflows/build-index.yml` (run it by hand with the `max_works` input). Artist names that are only Wikidata ids (like Q155626) are blanked.

## How the script is laid out (search for these headers in `index.html`)
state, sections, helpers, storage, filtering and sorting, rendering, favourites, actions, sheet (the edit page), museum label (placard) scanning, photo viewer, map, backup and restore, backup bookkeeping, Wikidata lookup, host services, on-device photo storage, start.
CSS uses a prefix per feature: `ts-` tour scenes, `br-` Browse a museum's notable works, `v…` and `tap-hint` photo viewer, `recog-` recognition, `wp-` the edit page. New CSS gets its own prefix.

## Standards we agreed on (keep every screen to these)
- **Back** goes to the page you were just on. **Done** (also Add to gallery, Save and next, Delete) closes the screen and goes to the main page, never back to the viewer. Back buttons are the same size, shape and position everywhere (`.wp-back`, `.vback`, `.br-back`); only the colours match their page. Check with the viewer and edit page: both Back buttons must measure the same.
- **Favourite star**: a 44px circle at the bottom left, identical position on the viewer and the edit page. On the edit page the order along the bottom is star, ⋯, then Done.
- **Viewer**: Back top left, title and artist top right (20px italic), star bottom left, Details bottom right. Tapping the photo hides all the chrome.
- **Edit page**: top has Back and, right of it, "N to add". The row under the photo has "N to add" on the left and the To see / Seen pill always on the right.
- **Subject**, **Medium** and **Movement** are rows that open a bottom sheet with the same look.
- Motion is soft: layers listed in `SOFT_LAYERS` fade; add new overlays to that list.
- Wording is plain and human. A work is "missing" something if photo, title, artist, year, medium, movement, subject, museum, or city and country are empty (`missingInfo`).

## Behaviour worth knowing
- Tapping a work in Gallery view opens the photo viewer. In List and Timeline it opens the info (edit) page. There are no expanded rows any more.
- Autofill: Wikidata lookup (`wikiLookup`) fills artist, year, medium, movement, subject, museum, city and country. The recognise button finds the work from the photo using the CLIP model in the browser (transformers.js, loaded from a CDN on first use) and the index in `data/`, then runs the same lookup using the matched Wikidata id.
- **Scan placard** reads a museum label on the phone with no AI and no cost: `readPlacard` uses AI only if `aiOn()`, otherwise `readPlacardOnPhone`, which runs Tesseract.js (loaded from jsdelivr on first use, English and Italian, cached after) on a grey, shrunk copy of the photo, then `parseLabel` guesses artist, title, year and medium from the lines. It then runs the normal Wikidata autofill on the title. It is a best guess; the owner checks it. It could not be tested against real OCR in the sandbox (no network), only with a stand-in for Tesseract and typed label text. To add a language, add it to `OCR_LANGS`.
- Recognition looks at the centred square of the photo plus, for wide or tall photos, the two end squares (counted 3% less). Wikidata calls retry once, and the title search also asks for paintings only (`haswbstatement:P31=Q3305213`) because plain search can bury the right painting.
- The first-time download note for the recogniser shows only once (`gallery-ledger-recog-dl`).
- Examples: ten sample works with photos embedded in the page so they work offline; they are seeded once after the tour (`gallery-ledger-seeded`).
- Backups are JSON with photos in base64. `buildBackup` copies all fields, but the import has a whitelist of fields: add new fields there too.

## Removed on purpose (do not rebuild without asking)
- Wikipedia descriptions ("about" text) on works: removed because they were hard to find. Old saved ones are cleared on load.
- Expanded rows in List and Timeline, the add-work wizard steps, the old detail card.
- Mixed leftovers cleaned in two passes; if something looks unused it probably still is. Check that a name is referenced before deleting.

## Still in the code but not reachable on the phone
- The AI branches (AI autofill and the AI version of reading a label), and the Claude-hosted storage mode (`coll`, `mcoll`, `hostService('db')`). They only run when the app is hosted inside Claude. Kept in case an AI route is added later. Removing the storage branch touches save, delete, load and backup, so test those and ask for a fresh backup first.

## Optional AI: rules for keeping the door open
The app must work fully with no AI and no running costs (this is the case today: recognition runs on the phone, autofill uses Wikidata, hosting is free). AI is an optional extra: find it by searching for `aiOn()` and `sampleFn`. Rules: an AI feature is a button that stays hidden unless AI is available (like Scan placard); it runs only when the owner taps it, never in the background; nothing else may depend on it; if an AI server is ever added, it is a separate paid service, so say so before connecting it.

## Parked ideas
Install-as-an-app guide slide; app rename (the owner likes "Placard"); a Room field and Met/Chicago museum connectors (advised against broad connectors); artist birth/death years; photo for works added from Notable works (Wikimedia Commons image, public-domain only, test on the phone first); real iCloud backup.

## How we work
1. Recommend, build, test, commit, push, then tell the owner in a few plain lines what changed and what could not be tested on their phone.
2. Bump the version stamp (`Version YYYY-MM-DD HH:MM`, shown in the ⋯ menu as `#buildLine`) on every pushed change so the owner can tell the update arrived.
3. Always `git pull --rebase origin main` before pushing: the index Action also pushes to `main`.
4. Commit messages end with the two attribution lines the session asks for.
5. Test with Playwright at 390 x 800 against a local static server. The sandbox cannot reach Wikidata, Wikipedia, Wikimedia or Hugging Face, so anything that needs them can only be checked on the owner's phone. Playwright's `page.route` does not catch service-worker fetches; use the context's `route`.
6. For cleanups, compare screenshots of every main screen before and after and require them to be identical.
