"""Second pass: titles whose first lookup hit the wrong Wikipedia article.

Each entry is (seed title, search query, accepted article title prefix).
Verified hits overwrite posters.json; misses fall back to the designed card.
"""
import json
import os
import time
import urllib.parse
import urllib.request

UA = {"User-Agent": "CineBite-seed-script/1.0 (movie poster lookup)"}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "posters.json")

# (seed title, search query, expected wiki article title)
RETRY = [
    ("Line of Control", "Line of Control 2026 film Kashmir war", "Line of Control"),
    ("Bhediya 2", "Bhediya 2 Varun Dhawan 2026", "Bhediya"),
    ("The Paradise", "The Paradise 2026 film Nani", "Paradise"),
    ("Udta Teer", "Udta Teer Ayushmann Khurrana film", "Udta"),
    ("Ranabaali", "Ranabaali Vijay Deverakonda Rashmika", "Ranabaali"),
    ("Raftaar", "Raftaar 2026 film Rajkummar Rao", "Raft"),
    ("Ramayana", "Ramayana 2026 film Ranbir Kapoor Nitesh Tiwari", "Ramayana"),
    ("King", "King 2026 film Shah Rukh Khan Sujoy Ghosh", "King"),
    ("Tumbbad 2", "Tumbbad 2 2026 film Sohum Shah", "Tumbbad"),
    ("Ranger", "Ranger 2026 film Akshay Kumar Anees Bazmee", "Ranger"),
    ("Bail", "Bail 2026 Kannada film Shivarajkumar", "Bail"),
    ("Don't Trouble The Trouble", "Dont Trouble The Trouble Fahadh Faasil film", "Don"),
]


def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if "429" in str(e) and i < tries - 1:
                time.sleep(6 * (i + 1))
                continue
            raise
    return None


def lookup(query, expect):
    res = get("https://en.wikipedia.org/w/api.php?action=query&list=search"
              f"&srsearch={urllib.parse.quote(query)}&srlimit=6&format=json")
    for hit in res.get("query", {}).get("search", []):
        title = hit["title"]
        if not title.lower().startswith(expect.lower()):
            continue
        if "list of" in title.lower() or "disambiguation" in title.lower():
            continue
        s = get("https://en.wikipedia.org/api/rest_v1/page/summary/"
                f"{urllib.parse.quote(title.replace(' ', '_'))}")
        img = (s.get("originalimage") or {}).get("source") or \
              (s.get("thumbnail") or {}).get("source")
        return {
            "poster": img.split("?")[0] if img else None,
            "wiki_title": s.get("title"),
            "description": s.get("description", ""),
            "extract": (s.get("extract") or "")[:260],
        }
    return {"poster": None, "error": f"no article matching '{expect}'"}


def main():
    with open(OUT, encoding="utf-8") as fh:
        data = json.load(fh)
    for key, query, expect in RETRY:
        try:
            r = lookup(query, expect)
        except Exception as e:
            r = {"poster": None, "error": str(e)}
        if r.get("poster"):
            data[key] = r
        elif data.get(key, {}).get("poster") and not data[key].get("_checked"):
            # keep nothing unverified: mark the earlier bad hit for review
            data[key] = r
        else:
            data[key] = {**data.get(key, {}), **r}
        print(f"{'OK  ' if data[key].get('poster') else 'MISS'} {key:30s} -> "
              f"{data[key].get('wiki_title')} | {data[key].get('description', '')[:44]}")
        if data[key].get("poster"):
            print(f"       {data[key]['poster']}")
        with open(OUT, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        time.sleep(3)
    print(f"\n{sum(1 for v in data.values() if v.get('poster'))}/{len(data)} with posters")


if __name__ == "__main__":
    main()
