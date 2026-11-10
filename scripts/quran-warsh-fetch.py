"""Miroir des donnees du Coran (Warsh) depuis surahquran.com vers le depot.

Sources :
  - index   : https://surahquran.com/warsh/fahras.html
  - sourate : https://surahquran.com/warsh/<n>.html

Sorties :
  assets/data/quran-index.json      -> liste des 114 sourates
  assets/data/quran-warsh/<n>.json   -> versets de chaque sourate
"""

import urllib.request, re, json, datetime, os, sys, time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_INDEX = os.path.join(BASE, "assets", "data", "quran-index.json")
OUT_DIR = os.path.join(BASE, "assets", "data", "quran-warsh")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}


def get(url):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=45).read().decode("utf-8", "replace")


def clean(t):
    t = re.sub(r"<[^>]+>", "", t)
    return re.sub(r"\s+", " ", t).strip()


def parse_index(html):
    rows = []
    i = html.find("قم باختيار سورة من الفهرس")
    zone = html[i:] if i >= 0 else html
    # le HTML de la source n'a pas de <tr> : on s'appuie sur les <th>N</th>
    for m in re.finditer(
        r"<th>\s*(\d{1,3})\s*</th>\s*"
        r"<td>\s*<a[^>]*href=\"?\d+\.html\"?[^>]*>(.*?)</a>\s*</td>\s*"
        r"<td>\s*((?:مكي|مدني)[^\s<]*)\s*</td>\s*"
        r"<td>\s*(\d{1,4})\s*</td>\s*"
        r"<td>\s*(\d{1,4})\s*</td>",
        zone, re.S):
        num, name, typ, count, page = m.groups()
        t = re.sub(r"[ً-ْٰـ]", "", typ)
        rows.append({
            "n": int(num),
            "name": clean(name),
            "type": "مكية" if t.startswith("مكي") else "مدنية",
            "count": int(count),
            "page": int(page),
        })
    return rows


DIAC = "\u064B-\u0652\u0670\u0653-\u0655\u06D6-\u06ED\u08F0-\u08F3\u08CC\u0870\u0898"


def strip_basmala_text(s):
    """Retire la basmala textuelle (سورة 1) du debut du texte."""
    t = s.lstrip()
    target = "\u0628\u0633\u0645\u0627\u0644\u0644\u0647\u0627\u0644\u0631\u062d\u0645\u0646\u0627\u0644\u0631\u062d\u064a\u0645"
    plain = ""
    i = 0
    while i < len(t):
        ch = t[i]
        is_diac = re.match("[" + DIAC + "]", ch)
        if not is_diac and ch != " ":
            plain += ch
        i += 1
        if not target.startswith(plain):
            if not is_diac and ch != " ":
                i -= 1
            break
        if plain == target:
            break
    if plain == target:
        return re.sub("^[" + DIAC + "\\s]+", "", t[i:].lstrip())
    return s


def parse_surah(html, n):
    # zone de lecture
    m = re.search(r'<div class="quran">(.*?)</div>', html, re.S)
    if not m:
        return []
    zone = m.group(1)
    zone = re.sub(r"<a\s+h2[^>]*>.*?</a>", " ", zone, flags=re.S)   # titre "سورة X للقراءة..."
    zone = re.sub(r"<p>\s*<img[^>]*/>\s*</p>", " @@BASMALA@@ ", zone)
    p = zone.find("@@BASMALA@@")
    if p >= 0:
        zone = zone[p + len("@@BASMALA@@"):]
    zone = re.sub(r"<br\s*/?>", " ", zone)
    zone = re.sub(r"<[^>]+>", " ", zone)
    p = zone.find("لا تنسنا من دعوة")
    if p > 0:
        zone = zone[:p]
    zone = re.sub(r"\s+", " ", zone).strip()
    zone = strip_basmala_text(zone)
    # separation des versets : le numero suit le verset -> texte precedent
    parts = re.split(r"\((\d{1,3})\)", zone)
    verses = []
    for i in range(1, len(parts) - 1, 2):
        num = int(parts[i])
        txt = parts[i - 1].strip()
        if txt:
            verses.append({"n": num, "t": txt})
    # dernier fragment (apres le dernier numero) = dernier verset
    tail = parts[-1].strip()
    if tail:
        verses.append({"n": (verses[-1]["n"] + 1) if verses else 1, "t": tail})
    return verses


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    index_html = get("https://surahquran.com/warsh/fahras.html")
    rows = parse_index(index_html)
    if len(rows) < 100:
        print("ECHEC : index parse =", len(rows), "lignes")
        sys.exit(1)
    print("Index parse :", len(rows), "sourates")
    index = []
    for row in rows:
        n = row["n"]
        try:
            html = get("https://surahquran.com/warsh/%d.html" % n)
            verses = parse_surah(html, n)
        except Exception as e:
            print("  ! surah", n, e)
            verses = []
        data = {
            "n": n,
            "name": row["name"],
            "type": row["type"],
            "count": row["count"],
            "page": row["page"],
            "verses": verses,
        }
        with open(os.path.join(OUT_DIR, "%d.json" % n), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        index.append({"n": n, "name": row["name"], "type": row["type"], "count": row["count"], "page": row["page"]})
        print("  %3d %-14s %-6s %4d versets" % (n, row["name"], row["type"], len(verses)), flush=True)
        time.sleep(0.35)

    payload = {
        "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "https://surahquran.com/warsh/fahras.html",
        "riwaya": "ورش عن نافع",
        "surahs": index,
    }
    with open(OUT_INDEX, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print("Index ecrit :", OUT_INDEX)


if __name__ == "__main__":
    main()
