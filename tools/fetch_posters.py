"""Fetch real poster artwork for the 2026 movie slate from Wikipedia.

Rate-limit friendly (polite delay + backoff) and resumable: existing hits in
posters.json are kept, only missing titles are retried.
"""
import json
import os
import time
import urllib.parse
import urllib.request

UA = {"User-Agent": "CineBite-seed-script/1.0 (movie poster lookup)"}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "posters.json")

TITLES = [
    "Drishyam 3", "Pooja Meri Jaan", "Prem Keetanu", "Verity", "Soulm8te",
    "Tom and Jerry: Forbidden Compass", "Line of Control",
    "Insidious: Out of the Further", "Mirzapur: The Movie", "Lust Stories 3",
    "Bhediya 2", "The Paradise", "Fall 2: Deadpoint", "Heart of the Beast",
    "Primetime", "Udta Teer", "Bokshi", "Jailer 2", "Raftaar", "Ranabaali",
    "OM Chapter-1", "Practical Magic 2", "Ramayana", "King", "Tumbbad 2",
    "Ranger",
]


def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if "429" in str(e) and i < tries - 1:
                wait = 6 * (i + 1)
                print(f"      rate limited, waiting {wait}s ...")
                time.sleep(wait)
                continue
            raise
    return None


def clean(url):
    return url.split("?")[0] if url else None


def lookup(title):
    q = urllib.parse.quote(title)
    res = get(f"https://en.wikipedia.org/w/api.php?action=query&list=search"
              f"&srsearch={q}&srlimit=4&format=json")
    hits = res.get("query", {}).get("search", [])
    if not hits:
        return {"poster": None, "error": "no article"}
    best = hits[0]["title"]
    s = get(f"https://en.wikipedia.org/api/rest_v1/page/summary/"
            f"{urllib.parse.quote(best.replace(' ', '_'))}")
    img = (s.get("originalimage") or {}).get("source") or \
          (s.get("thumbnail") or {}).get("source")
    return {
        "poster": clean(img),
        "wiki_title": s.get("title"),
        "description": s.get("description", ""),
        "extract": (s.get("extract") or "")[:260],
    }


def main():
    data = {}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as fh:
            data = json.load(fh)
    for t in TITLES:
        if data.get(t, {}).get("poster"):
            continue
        try:
            r = lookup(t)
        except Exception as e:
            r = {"poster": None, "error": str(e)}
        data[t] = r
        print(f"{'OK  ' if r.get('poster') else 'MISS'} {t:38s} -> "
              f"{r.get('wiki_title')} | {r.get('description', '')[:46]}")
        if r.get("poster"):
            print(f"       {r['poster']}")
        with open(OUT, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        time.sleep(3)
    have = sum(1 for v in data.values() if v.get("poster"))
    print(f"\nsaved posters.json ({have}/{len(TITLES)} posters)")


if __name__ == "__main__":
    main()
