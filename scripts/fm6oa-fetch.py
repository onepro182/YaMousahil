import urllib.request, re, json, datetime, os, sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CITIES = {
    "casablanca": 15,
    "rabat": 1,
    "fes": 106,
    "marrakech": 40,
    "oujda": 78,
    "tangier": 60,
    "agadir": 151,
    "meknes": 124,
}
KEYS = ["fajr", "dhuhr", "asr", "maghrib", "isha"]

out = {}
for key, code in CITIES.items():
    url = "https://fm6oa.org/prieres/code/index.php?ville=%d" % code
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace")

    # nom de ville depuis la liste d'options
    name = None
    mo = re.search(r'<option[^>]*value="index\.php\?ville=%d"[^>]*>([^<]+)</option>' % code, html)
    if mo:
        name = mo.group(1).strip()

    # tableau du jour : thead avec الفجر .. العشاء
    times = []
    mt = re.search(r"<thead>\s*<tr>\s*<th>\s*الفجر\s*</th>.*?</tr>\s*</thead>\s*<tbody>(.*?)</tbody>", html, re.S)
    if mt:
        tds = re.findall(r"<td[^>]*>(.*?)</td>", mt.group(1), re.S)
        for t in tds[:5]:
            v = re.sub(r"<[^>]+>", "", t)
            v = re.sub(r"\s+", " ", v).strip()
            if re.match(r"^\d{1,2}:\d{2}$", v):
                times.append(v)

    # date grégorienne
    greg = None
    mg = re.search(r"التاريخ الميلادي\s*</th>\s*<td>(.*?)</td>", html, re.S)
    if mg:
        greg = re.sub(r"<[^>]+>", "", mg.group(1))
        greg = re.sub(r"\s+", " ", greg).strip()

    out[key] = {"code": code, "name": name or key, "greg": greg or "", "times": dict(zip(KEYS, times))}
    print(key, name, times, greg, flush=True)

payload = {
    "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "day": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).strftime("%Y-%m-%d"),
    "cities": out,
}
os.makedirs(os.path.join(BASE, "assets", "data"), exist_ok=True)
with open(os.path.join(BASE, "assets", "data", "fm6oa-times.json"), "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=1)
print("JSON ecrit:", os.path.join(BASE, "assets", "data", "fm6oa-times.json"))
