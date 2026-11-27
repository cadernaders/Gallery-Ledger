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

MIN_LINKS = int(os.environ.get("MIN_LINKS", "5"))      # how widely a work is covered on Wikipedia
MAX_WORKS = int(os.environ.get("MAX_WORKS", "12000"))
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

def fetch_works():
    works, seen = [], set()
    page, step = 0, 1500
    while len(works) < MAX_WORKS:
        q = f"""SELECT ?w ?wLabel ?aLabel ?year ?img ?links WHERE {{
          ?w wdt:P31 wd:Q3305213; wdt:P18 ?img; wikibase:sitelinks ?links. FILTER(?links >= {MIN_LINKS})
          OPTIONAL {{ ?w wdt:P170 ?a. }} OPTIONAL {{ ?w wdt:P571 ?inc. BIND(YEAR(?inc) AS ?year) }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". ?w rdfs:label ?wLabel. ?a rdfs:label ?aLabel. }}
        }} ORDER BY DESC(?links) LIMIT {step} OFFSET {page * step}"""
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
            works.append([qid, title, b.get("aLabel", {}).get("value", ""), b.get("year", {}).get("value", ""), img.rsplit("/", 1)[-1]])
        page += 1
        print("works so far", len(works), file=sys.stderr)
    return works[:MAX_WORKS]

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

    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for i, (w, im) in enumerate(zip(works, ex.map(download, works))):
            if im is None:
                continue
            batch_w.append(w); batch_i.append(im)
            if len(batch_i) >= 32:
                flush()
            if i % 500 == 0:
                print("embedded", len(kept), "of", i, file=sys.stderr)
    flush()
    os.makedirs("data", exist_ok=True)
    with open("data/paintings.json", "w", encoding="utf-8") as fh:
        json.dump(kept, fh, ensure_ascii=False, separators=(",", ":"))
    np.stack(vecs).astype(np.int8).tofile("data/paintings.bin")
    print("done", len(kept), "paintings")

if __name__ == "__main__":
    main()
