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


def clean(t):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", t)).strip()


def parse_today(html):
    times = []
    mt = re.search(r"<thead>\s*<tr>\s*<th>\s*الفجر\s*</th>.*?</tr>\s*</thead>\s*<tbody>(.*?)</tbody>", html, re.S)
    if mt:
        tds = re.findall(r"<td[^>]*>(.*?)</td>", mt.group(1), re.S)
        for t in tds[:5]:
            v = clean(t)
            if re.match(r"^\d{1,2}:\d{2}$", v):
                times.append(v)
    greg = None
    mg = re.search(r"التاريخ الميلادي\s*</th>\s*<td>(.*?)</td>", html, re.S)
    if mg:
        greg = clean(mg.group(1))
    name = None
    mo = None
    return times, greg


def parse_month(html):
    hijri_month = None
    greg_month = None
    hm = re.search(r'<th class="wakt">\s*(.*?)\s*</th>\s*<th class="wakt">\s*(.*?)\s*</th>\s*<th class="wakt">الفجر', html, re.S)
    if hm:
        hijri_month = clean(hm.group(1))
        greg_month = clean(hm.group(2))
    mt = re.search(r'<table id="horaire".*?</thead>\s*<tbody>(.*?)</tbody>', html, re.S)
    rows = []
    if mt:
        trs = re.findall(r"<tr[^>]*>(.*?)</tr>", mt.group(1), re.S)
        for tr in trs:
            tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
            if len(tds) < 9:
                continue
            vals = [clean(t) for t in tds[:9]]
            is_today = 'class="active"' in tr or "class='active'" in tr
            rows.append({
                "weekday": vals[0],
                "hijriDay": vals[1],
                "gregDate": vals[2],
                "fajr": vals[3],
                "shurooq": vals[4],
                "dhuhr": vals[5],
                "asr": vals[6],
                "maghrib": vals[7],
                "isha": vals[8],
                "today": is_today,
            })
    return hijri_month, greg_month, rows


out = {}
for key, code in CITIES.items():
    url = "https://fm6oa.org/prieres/code/index.php?ville=%d" % code
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace")

    name = None
    mo = re.search(r'<option[^>]*value="index\.php\?ville=%d"[^>]*>([^<]+)</option>' % code, html)
    if mo:
        name = mo.group(1).strip()

    times, greg = parse_today(html)
    hijri_month, greg_month, month_rows = parse_month(html)

    out[key] = {
        "code": code,
        "name": name or key,
        "greg": greg or "",
        "times": dict(zip(KEYS, times)),
        "month": {
            "hijri": hijri_month or "",
            "gregorian": greg_month or "",
            "rows": month_rows,
        },
    }
    print(key, name, len(month_rows), "rows", flush=True)

payload = {
    "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "day": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).strftime("%Y-%m-%d"),
    "cities": out,
}
os.makedirs(os.path.join(BASE, "assets", "data"), exist_ok=True)
with open(os.path.join(BASE, "assets", "data", "fm6oa-times.json"), "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=1)
print("JSON ecrit:", os.path.join(BASE, "assets", "data", "fm6oa-times.json"))