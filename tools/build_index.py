"""Builds the painting-recognition index for Gallery Ledger.

Runs on GitHub (see .github/workflows/build-index.yml), because GitHub's computers can reach Wikimedia.
Output (written to data/):
  paintings.json  list of [wikidataId, title, artist, year, commonsFile]
  paintings.bin   int8 image fingerprints, 512 numbers per painting, in the same order
The app compares a photo's fingerprint against these to suggest which work it is.
"""
import io, json, os, sys, time, concurrent.futures as cf
import requests
from PIL import Image
import numpy as np

MIN_LINKS = int(os.environ.get("MIN_LINKS", "3"))      # how widely a work is covered on Wikipedia
MAX_WORKS = int(os.environ.get("MAX_WORKS", "16000"))
UA = {"User-Agent": "GalleryLedgerIndexBuilder/1.0 (https://github.com/cadernaders/Gallery-Ledger)"}
SPARQL = "https://query.wikidata.org/sparql"

def sparql(q):
    for attempt in range(4):
        try:
            r = requests.get(SPARQL, params={"query": q, "format": "json"}, headers=UA, timeout=120)
            if r.status_code == 200:
                return r.json()["results"]["bindings"]
            print("sparql", r.status_code, file=sys.stderr)
        except Exception as e:
            print("sparql error", e, file=sys.stderr)
        time.sleep(5 * (attempt + 1))
    return []

# Wikipedia-coverage bands, most famous first. Asking for one band at a time keeps every query small enough for
# Wikidata to answer (one big sorted query for tens of thousands of paintings times out).
BANDS = [(100, 10**6), (50, 99), (30, 49), (20, 29), (15, 19), (12, 14), (10, 11), (8, 9), (7, 7), (6, 6), (5, 5), (4, 4), (3, 3), (2, 2)]

def fetch_works():
    works, seen = [], set()
    step = 1500
    for lo, hi in BANDS:
        if hi < MIN_LINKS or len(works) >= MAX_WORKS:
            continue
        lo = max(lo, MIN_LINKS)
        page = 0
        while len(works) < MAX_WORKS:
            q = f"""SELECT ?w ?wLabel ?aLabel ?year ?img WHERE {{
              ?w wdt:P31 wd:Q3305213; wdt:P18 ?img; wikibase:sitelinks ?links. FILTER(?links >= {lo} && ?links <= {hi})
              OPTIONAL {{ ?w wdt:P170 ?a. }} OPTIONAL {{ ?w wdt:P571 ?inc. BIND(YEAR(?inc) AS ?year) }}
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". ?w rdfs:label ?wLabel. ?a rdfs:label ?aLabel. }}
            }} ORDER BY ?w LIMIT {step} OFFSET {page * step}"""
            rows = sparql(q)
            if not rows:
                break
            for b in rows:
                qid = b["w"]["value"].rsplit("/", 1)[-1]
                title = b.get("wLabel", {}).get("value", "")
                if qid in seen or not title or title.startswith("Q"):
                    continue
                seen.add(qid)
                img = b["img"]["value"]
                artist = b.get("aLabel", {}).get("value", "")
                if artist.startswith("Q") and artist[1:].isdigit():
                    artist = ""  # no English label
                works.append([qid, title, artist, b.get("year", {}).get("value", ""), img.rsplit("/", 1)[-1]])
            page += 1
            print(f"band {lo}-{hi}: works so far", len(works), file=sys.stderr)
            if len(rows) < step:
                break
    return works[:MAX_WORKS]

def load_old():
    """The index we already have: work id -> (row, fingerprint), so known paintings are not downloaded again."""
    try:
        rows = json.load(open("data/paintings.json", encoding="utf-8"))
        vecs = np.fromfile("data/paintings.bin", dtype=np.int8)
        if len(vecs) != len(rows) * 512:
            return {}
        vecs = vecs.reshape(len(rows), 512)
        return {r[0]: (r, vecs[i]) for i, r in enumerate(rows)}
    except Exception as e:
        print("no usable old index:", e, file=sys.stderr)
        return {}

def download(work):
    url = "https://commons.wikimedia.org/wiki/Special:FilePath/" + work[4] + "?width=300"
    for attempt in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=60)
            if r.status_code == 200:
                return Image.open(io.BytesIO(r.content)).convert("RGB")
            if r.status_code == 429:
                time.sleep(10 * (attempt + 1))
        except Exception:
            time.sleep(2)
    return None

def main():
    import torch
    from transformers import CLIPModel, CLIPProcessor
    works = fetch_works()
    print("total works", len(works))
    old = load_old()
    print("already indexed", len(old))
    if old and len(works) < 0.5 * len(old):
        sys.exit("Wikidata gave far fewer works than the current index; leaving the index as it is.")
    todo = [w for w in works if w[0] not in old]
    print("new to embed", len(todo))
    model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").eval()
    proc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    kept, vecs = [], []
    batch_w, batch_i = [], []

    def flush():
        if not batch_i:
            return
        with torch.no_grad():
            inp = proc(images=batch_i, return_tensors="pt")
            vo = model.vision_model(pixel_values=inp["pixel_values"])
            f = model.visual_projection(vo.pooler_output)
            f = torch.nn.functional.normalize(f, dim=-1).numpy()
        for w, v in zip(batch_w, f):
            kept.append(w)
            vecs.append(np.clip(np.round(v * 127), -127, 127).astype(np.int8))
        batch_w.clear(); batch_i.clear()

    # keep the fingerprints we already have for works that are still wanted (refreshing title, artist and year)
    for w in works:
        if w[0] in old:
            kept.append(w); vecs.append(old[w[0]][1])
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for i, (w, im) in enumerate(zip(todo, ex.map(download, todo))):
            if im is None:
                continue
            batch_w.append(w); batch_i.append(im)
            if len(batch_i) >= 32:
                flush()
            if i % 500 == 0:
                print("embedded", len(kept), "of", i, file=sys.stderr)
    flush()
    if len(kept) < 0.9 * len(old):
        sys.exit("The new index would be smaller than the current one; leaving the index as it is.")
    os.makedirs("data", exist_ok=True)
    with open("data/paintings.json", "w", encoding="utf-8") as fh:
        json.dump(kept, fh, ensure_ascii=False, separators=(",", ":"))
    np.stack(vecs).astype(np.int8).tofile("data/paintings.bin")
    print("done", len(kept), "paintings")

if __name__ == "__main__":
    main()
