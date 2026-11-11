#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Miroir des donnees "sante" de sihamaroc.com vers assets/data/siha/

Produit :
  assets/data/siha/pharmacies/<ville>.json   pharmacies de garde + annuaire
  assets/data/siha/cliniques/<ville>.json    cliniques (tel, adresse, coordonnees)
  assets/data/siha/laboratoires/<ville>.json laboratoires d'analyses (tel, adresse)
  assets/data/siha/medecins/<ville>.json     medecins par specialite (adresse, tel)
  assets/data/siha/tarifs.json               tarifs des analyses medicales (national)

Source : https://sihamaroc.com
"""
import json
import os
import re
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "https://sihamaroc.com"
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
OUT_DIR = os.path.join(ROOT, "assets", "data", "siha")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# (slug sihamaroc, nom arabe) - une ville sans donnee est simplement ignoree
CITIES = [
    ("oujda", "وجدة"),
    ("casablanca", "الدار البيضاء"),
    ("rabat", "الرباط"),
    ("fes", "فاس"),
    ("marrakech", "مراكش"),
    ("tanger", "طنجة"),
    ("kenitra", "القنيطرة"),
    ("agadir", "أكادير"),
    ("meknes", "مكناس"),
    ("nador", "الناظور"),
    ("sale", "سلا"),
    ("safi", "آسفي"),
    ("el-jadida", "الجديدة"),
    ("mohammedia", "المحمدية"),
    ("beni-mellal", "بني ملال"),
    ("khouribga", "خريبكة"),
    ("berkane", "بركان"),
    ("tiznit", "تيزنيت"),
    ("essaouira", "الصويرة"),
    ("ouarzazate", "ورزازات"),
    ("taourirt", "تاوريرت"),
    ("khemisset", "الخميسات"),
    ("berrechid", "بر rechid".replace(" rechid", "ريد")),
    ("temara", "تمارة"),
    ("ait-melloul", "آيت ملول"),
]

# Villes pour lesquelles on recupere les fiches detaillees (cliniques / laboratoires)
# : le site limite le debit, on priorise les grandes villes.
DETAIL_CITIES = [
    ("oujda", "وجدة"), ("casablanca", "الدار البيضاء"), ("rabat", "الرباط"),
    ("fes", "فاس"), ("marrakech", "مراكش"), ("tanger", "طنجة"),
    ("kenitra", "القنيطرة"), ("agadir", "أكادير"), ("meknes", "مكناس"),
    ("nador", "الناظور"),
]

# Les medecins exigent 1 requete par specialite : on limite les villes
# detaillees pour rester sous la limite de debit du site.
DOCTOR_CITIES = [
    ("oujda", "وجدة"), ("casablanca", "الدار البيضاء"), ("rabat", "الرباط"), ("fes", "فاس"),
]

_cache = {}
_disk_cache = os.path.join(ROOT, ".cache", "siha")
_MIN_INTERVAL = 12.0          # ~5 requetes/min : rythme accepte par sihamaroc (429 au-dela)
_last_request = [0.0]
_rate_lock = threading.Lock()

# Contexte TLS verifie (utilise par defaut). Si la chaine de certificats presente
# un intermediaire perime (certaines versions de cacert embarquent un intermediaire
# expire), on bascule sur un contexte non verifie : le site est public, en lecture
# seule, et la feuille servie est valide (expiree le 16/01/2027).
_CTX_VERIFIED = ssl.create_default_context()
_CTX_RELAXED = ssl.create_default_context()
_CTX_RELAXED.check_hostname = False
_CTX_RELAXED.verify_mode = ssl.CERT_NONE
_ssl_mode = {"relaxed": False}


def _throttle():
    """Espace les requetes pour ne pas se faire bloquer (HTTP 429)."""
    with _rate_lock:
        wait = _MIN_INTERVAL - (time.time() - _last_request[0])
        if wait > 0:
            time.sleep(wait)
        _last_request[0] = time.time()


def _cache_path(url):
    import hashlib
    return os.path.join(_disk_cache, hashlib.sha1(url.encode("utf-8")).hexdigest() + ".html")


def fetch(url, tries=4):
    """Recupere une page (cache disque + memoire + retries + limitation de debit)."""
    if url in _cache:
        return _cache[url]
    # cache disque : evite de re-questeter le site (relance locale)
    if not _ssl_mode["relaxed"] or True:
        cp = _cache_path(url)
        if os.path.exists(cp):
            try:
                with open(cp, "r", encoding="utf-8") as f:
                    html = f.read()
                _cache[url] = html
                return html
            except Exception:
                pass
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "fr-FR,fr;q=0.9",
            })
            ctx = _CTX_RELAXED if _ssl_mode["relaxed"] else _CTX_VERIFIED
            _throttle()
            with urllib.request.urlopen(req, timeout=45, context=ctx) as resp:
                raw = resp.read()
            html = raw.decode("utf-8", "replace")
            _cache[url] = html
            try:
                os.makedirs(_disk_cache, exist_ok=True)
                with open(_cache_path(url), "w", encoding="utf-8", newline="") as f:
                    f.write(html)
            except Exception:
                pass
            return html
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (404, 410):
                _cache[url] = None
                return None
            if e.code == 429:
                pause = 15 * (attempt + 1)
                sys.stderr.write("  (429 - pause %ds sur %s)\n" % (pause, url.rsplit("/", 1)[-1][:40]))
                time.sleep(pause)
                continue
            time.sleep(1.2 * (attempt + 1))
        except Exception as e:  # noqa
            last = e
            reason = getattr(e, "reason", None)
            is_ssl = isinstance(e, ssl.SSLError) or isinstance(reason, ssl.SSLError)
            if is_ssl and not _ssl_mode["relaxed"]:
                _ssl_mode["relaxed"] = True
                sys.stderr.write("  (chaine TLS expiree -> mode non verifie)\n")
                continue
            time.sleep(1.2 * (attempt + 1))
    sys.stderr.write("  ! echec %s (%s)\n" % (url, last))
    _cache[url] = None
    return None


def unescape(s):
    s = s.replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
    s = s.replace("&lt;", "<").replace("&gt;", ">").replace("&nbsp;", " ")
    s = re.sub(r"&#x([0-9a-fA-F]+);", lambda m: chr(int(m.group(1), 16)), s)
    s = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), s)
    return s.strip()


def clean(s):
    return re.sub(r"\s+", " ", unescape(s or "")).strip()


def ld_json(html):
    """Retourne la liste des objets JSON-LD de la page."""
    out = []
    if not html:
        return out
    for m in re.finditer(r'<script type="application/ld\+json">([\s\S]*?)</script>', html):
        raw = m.group(1).strip()
        try:
            out.append(json.loads(raw))
        except Exception:
            pass
    return out


def split_sections(html):
    """Decoupe la page en sections <h2>titre</h2> ... contenu."""
    if not html:
        return []
    parts = re.split(r"<h2[^>]*>(.*?)</h2>", html, flags=re.S)
    sections = []
    for i in range(1, len(parts), 2):
        title = clean(parts[i])
        body = parts[i + 1]
        cut = body.find("<h2")
        if cut > 0:
            body = body[:cut]
        sections.append((title, body))
    return sections


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print("  -> %s (%d o)" % (os.path.relpath(path, ROOT).replace("\\", "/"), os.path.getsize(path)))


# ---------------------------------------------------------------- pharmacies
PH_ITEM = re.compile(
    r'<li><a href="/pharmacie/([^"]+)"[^>]*>(.*?)</a>(.*?)</li>', re.S)


def parse_pharmacies_html(html):
    """Extrait la liste HTML : nom / adresse / tel / info de garde."""
    items = []
    for m in PH_ITEM.finditer(html or ""):
        slug = m.group(1)
        nom = clean(m.group(2))
        rest = m.group(3)
        tel_m = re.search(r'href="tel:([^"]+)"[^>]*>(.*?)</a>', rest, re.S)
        tel = clean(tel_m.group(2)) if tel_m else ""
        garde_m = re.search(r"\(([^)]{0,60})\)</li>", rest, re.S)
        garde = clean(garde_m.group(1)) if garde_m else ""
        adresse = clean(re.sub(r'<a href="tel:[^"]*"[^>]*>.*?</a>', "", rest, flags=re.S))
        adresse = re.sub(r"^\s*[—–-]\s*", "", adresse)
        adresse = re.sub(r"\s*[—–-]\s*\([^)]*\)\s*$", "", adresse).strip(" —–-")
        if not tel and not adresse:
            continue
        items.append({"nom": nom, "slug": slug, "adresse": adresse, "tel": tel, "garde": garde})
    return items


def fetch_pharmacies(slug, ar_name):
    html = fetch("%s/pharmacies/%s" % (BASE, slug))
    if not html:
        return None
    garde, autres = [], []
    for title, body in split_sections(html):
        low = title.lower()
        if "garde" in low:
            for it in parse_pharmacies_html("<ul>" + body + "</ul>"):
                it["garde"] = it["garde"] or "de garde"
                garde.append(it)
        elif "autres pharmacies" in low:
            autres = parse_pharmacies_html("<ul>" + body + "</ul>")
    # JSON-LD : horaires + coordonnees precises des pharmacies de garde
    geo = {}
    for obj in ld_json(html):
        if obj.get("@type") == "ItemList":
            for entry in obj.get("itemListElement", []):
                it = entry.get("item", {})
                g = it.get("geo") or {}
                key = clean(it.get("name"))
                hours = it.get("specialOpeningHoursSpecification") or []
                if g.get("latitude") is not None:
                    geo[key] = {
                        "lat": g.get("latitude"),
                        "lon": g.get("longitude"),
                        "url": it.get("url", ""),
                        "heures": [("%s-%s" % (h.get("opens", ""), h.get("closes", ""))) for h in hours],
                    }
    for it in garde:
        g = geo.get(it["nom"])
        if g:
            it["lat"], it["lon"], it["url"] = g["lat"], g["lon"], g["url"]
            it["heures"] = g["heures"]
    for it in autres:
        g = geo.get(it["nom"])
        if g and "url" not in it:
            it["url"] = g["url"]
    return {"updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "ville": slug, "villeAr": ar_name,
            "garde": garde, "autres": autres}


# ---------------------------------------------------------------- cliniques
CL_ITEM = re.compile(r'<li><a href="/clinique/([^"]+)"[^>]*>(.*?)</a>(.*?)</li>', re.S)


def fetch_cliniques(slug, ar_name, with_detail=True):
    html = fetch("%s/cliniques/%s" % (BASE, slug))
    if not html:
        return None
    slugs, seen = [], set()
    for m in CL_ITEM.finditer(html):
        s = m.group(1)
        if s not in seen:
            seen.add(s)
            slugs.append((s, clean(m.group(2))))

    def detail(pair):
        s, nom = pair
        page = fetch("%s/clinique/%s" % (BASE, s))
        tel, addr, lat, lon = "", "", None, None
        if page:
            for obj in ld_json(page):
                if obj.get("@type") in ("MedicalClinic", "MedicalBusiness", "Hospital"):
                    tel = obj.get("telephone", "") or tel
                    a = obj.get("address") or {}
                    addr = a.get("streetAddress", "") or addr
                    g = obj.get("geo") or {}
                    lat = g.get("latitude", lat)
                    lon = g.get("longitude", lon)
        return {"nom": nom, "slug": s, "tel": tel, "adresse": addr, "lat": lat, "lon": lon,
                "url": "%s/clinique/%s" % (BASE, s)}

    items = []
    if slugs:
        if with_detail:
            with ThreadPoolExecutor(max_workers=1) as ex:
                items = list(ex.map(detail, slugs))
        else:
            items = [{"nom": n, "slug": s, "tel": "", "adresse": "", "lat": None, "lon": None,
                      "url": "%s/clinique/%s" % (BASE, s)} for s, n in slugs]
    return {"updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "ville": slug, "villeAr": ar_name, "items": items}


# ---------------------------------------------------------------- laboratoires
LAB_ITEM = re.compile(r'<li><a href="/laboratoire-analyse/([^"]+)"[^>]*>(.*?)</a>(.*?)</li>', re.S)


def fetch_laboratoires(slug, ar_name, with_detail=True):
    html = fetch("%s/laboratoires-analyses/%s" % (BASE, slug))
    if not html:
        return None
    slugs, seen = [], set()
    for m in LAB_ITEM.finditer(html):
        s = m.group(1)
        if s not in seen:
            seen.add(s)
            slugs.append((s, clean(m.group(2))))

    def detail(pair):
        s, nom = pair
        page = fetch("%s/laboratoire-analyse/%s" % (BASE, s))
        tel, addr, lat, lon = "", "", None, None
        if page:
            for obj in ld_json(page):
                if obj.get("@type") in ("MedicalBusiness", "MedicalClinic", "Laboratory"):
                    tel = obj.get("telephone", "") or tel
                    a = obj.get("address") or {}
                    addr = a.get("streetAddress", "") or addr
                    g = obj.get("geo") or {}
                    lat = g.get("latitude", lat)
                    lon = g.get("longitude", lon)
        return {"nom": nom, "slug": s, "tel": tel, "adresse": addr, "lat": lat, "lon": lon,
                "url": "%s/laboratoire-analyse/%s" % (BASE, s)}

    items = []
    if slugs:
        if with_detail:
            with ThreadPoolExecutor(max_workers=1) as ex:
                items = list(ex.map(detail, slugs))
        else:
            items = [{"nom": n, "slug": s, "tel": "", "adresse": "", "lat": None, "lon": None,
                      "url": "%s/laboratoire-analyse/%s" % (BASE, s)} for s, n in slugs]
    return {"updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "ville": slug, "villeAr": ar_name, "items": items}


# ---------------------------------------------------------------- medecins
MD_SPEC = re.compile(r'<li><a href="/medecins/([^/"]+)/([^"]+)"[^>]*>(.*?)</a>\s*\((\d+)\)</li>', re.S)
MD_ITEM = re.compile(r'<li><a href="/medecin/([^"]+)"[^>]*>(.*?)</a>(.*?)</li>', re.S)


def fetch_medecins(slug, ar_name, with_detail=True):
    html = fetch("%s/medecins/%s" % (BASE, slug))
    if not html:
        return None
    specs, seen = [], set()
    for m in MD_SPEC.finditer(html):
        city, spec, nom, nb = m.group(1), m.group(2), clean(m.group(3)), int(m.group(4))
        if spec in seen:
            continue
        seen.add(spec)
        specs.append({"slug": spec, "nom": nom, "nb": nb})

    # medecins visibles directement sur la page ville (nom + specialite)
    sample = []
    for m in MD_ITEM.finditer(html):
        rest = clean(m.group(3))
        spec = rest.lstrip(" —–-")
        sample.append({"nom": clean(m.group(2)), "specialite": spec, "specSlug": "",
                       "adresse": "", "tel": "", "url": "%s/medecin/%s" % (BASE, m.group(1))})

    def detail(spec):
        page = fetch("%s/medecins/%s/%s" % (BASE, slug, spec["slug"]))
        out = []
        if not page:
            return out
        for m in MD_ITEM.finditer(page):
            rest = m.group(3)
            tel_m = re.search(r'(\+?\d[\d\s().-]{7,20})\s*$', clean(rest))
            tel = clean(tel_m.group(1)) if tel_m else ""
            adresse = clean(re.sub(r'(\+?\d[\d\s().-]{7,20})\s*$', "", clean(rest)))
            adresse = re.sub(r"^[—–-]\s*", "", adresse).strip(" —–-")
            out.append({"nom": clean(m.group(2)), "specialite": spec["nom"], "specSlug": spec["slug"],
                        "adresse": adresse, "tel": tel, "url": "%s/medecin/%s" % (BASE, m.group(1))})
        return out

    doctors = []
    if with_detail and specs:
        with ThreadPoolExecutor(max_workers=1) as ex:
            for res in ex.map(detail, specs):
                doctors.extend(res)
    if not doctors:
        doctors = sample
    return {"updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "ville": slug, "villeAr": ar_name, "specialites": specs, "items": doctors,
            "complet": bool(with_detail and doctors and doctors is not sample)}


# ---------------------------------------------------------------- tarifs
TARIF_ITEM = re.compile(r'<li><a href="/tarif-analyse/([^"]+)"[^>]*>(.*?)</a>\s*:?\s*([^<]*)</li>', re.S)


def fetch_tarifs():
    html = fetch("%s/tarifs-analyses" % BASE)
    if not html:
        return None
    items = []
    for m in TARIF_ITEM.finditer(html):
        nom = clean(m.group(2))
        prix = clean(m.group(3))
        nums = re.findall(r"\d+(?:[.,]\d+)?", prix.replace(" ", " "))
        lo = hi = None
        if nums:
            vals = []
            for x in nums:
                try:
                    vals.append(float(x.replace(",", ".")))
                except ValueError:
                    pass
            if vals:
                lo, hi = min(vals), max(vals)
        items.append({"nom": nom, "slug": m.group(1), "prix": prix, "min": lo, "max": hi,
                      "url": "%s/tarif-analyse/%s" % (BASE, m.group(1))})
    return {"updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "items": items}


# ---------------------------------------------------------------- main
def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    only = args[0] if args else None
    if "--nocache" in sys.argv:
        import shutil
        shutil.rmtree(_disk_cache, ignore_errors=True)
    start = time.time()

    if not only or only == "tarifs":
        print("Tarifs des analyses...")
        t = fetch_tarifs()
        if t:
            write_json(os.path.join(OUT_DIR, "tarifs.json"), t)
        write_json(os.path.join(OUT_DIR, "villes.json"),
                   {"updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "villes": [{"slug": s, "ar": a} for s, a in CITIES]})

    jobs = []
    for slug, ar in CITIES:
        if only in (None, "pharmacies"):
            jobs.append(("pharmacies", slug, ar))
        if only in (None, "cliniques"):
            jobs.append(("cliniques", slug, ar))
        if only in (None, "laboratoires"):
            jobs.append(("laboratoires", slug, ar))
        if only in (None, "medecins"):
            jobs.append(("medecins", slug, ar))

    # les fiches detaillees ne sont recuperees que pour les villes prioritaires
    def run(job):
        kind, slug, ar = job
        fn = {"pharmacies": fetch_pharmacies, "cliniques": fetch_cliniques,
              "laboratoires": fetch_laboratoires, "medecins": fetch_medecins}[kind]
        # les fiches detaillees (telephone / adresse) ne sont recuperees que pour
        # les villes prioritaires : le site limite fortement le debit (HTTP 429).
        detail = True
        if kind in ("cliniques", "laboratoires", "medecins"):
            ref = DOCTOR_CITIES if kind == "medecins" else DETAIL_CITIES
            detail = (slug, ar) in ref
        try:
            data = fn(slug, ar, detail) if kind in ("cliniques", "laboratoires", "medecins") else fn(slug, ar)
        except Exception as e:  # noqa
            sys.stderr.write("  ! %s/%s : %s\n" % (kind, slug, e))
            return
        if not data:
            print("  - %s/%s : aucune donnee" % (kind, slug))
            return
        if kind == "pharmacies":
            n = len(data["garde"]) + len(data["autres"])
            if n == 0:
                return
        elif kind == "medecins":
            if not data["items"]:
                return
        elif not data["items"]:
            return
        write_json(os.path.join(OUT_DIR, kind, "%s.json" % slug), data)

    for kind in ("pharmacies", "cliniques", "laboratoires", "medecins"):
        todo = [j for j in jobs if j[0] == kind]
        if not todo:
            continue
        print("%s (%d villes)..." % (kind.capitalize(), len(todo)))
        with ThreadPoolExecutor(max_workers=1) as ex:
            list(ex.map(run, todo))

    print("Termine en %.1fs" % (time.time() - start))


if __name__ == "__main__":
    main()
