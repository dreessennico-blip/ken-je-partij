#!/usr/bin/env python3
"""Nachtelijke update van de app "Hoe goed ken jij je partij?".

Wat dit programma doet:
 1. Haalt moties op uit de open data van de Tweede Kamer (afgelopen weken, of alles met --diep).
 2. Neemt alleen moties met een uitslag die nog niet in de app staan.
 3. Haalt van elke nieuwe motie de PDF op en leest de tekst.
 4. Controleert alles. Een motie waar iets niet klopt, wordt NIET toegevoegd maar komt in het verslag.
 5. Voegt de goedgekeurde moties toe aan docs/index.html en schrijft verslag-laatste-run.md.
"""
import argparse, collections, datetime, glob, json, os, re, subprocess, sys, tempfile, time
import urllib.parse, urllib.request

BASIS = "https://gegevensmagazijn.tweedekamer.nl/OData/v4/2.0/"
STARTDATUM = datetime.datetime(2026, 2, 22, 23, 0, 0)          # 23 februari 2026, 00:00 Nederlandse tijd (UTC)
ALIAS = {"GroenLinks-PvdA": "PRO"}
MAANDEN = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober", "november", "december"]
# Rijksbegroting: Romeins cijfer (of letter) in het dossiernummer -> ministerie-groep van de app
BEG = {"A": "IW", "B": "BZK", "IV": "BZK", "V": "BZ", "VI": "JV", "VII": "BZK", "VIII": "OCW", "X": "DEF", "XII": "IW",
       "IX": "FIN", "III": "AZ", "XIII": "EZ", "XIV": "LVVN", "XV": "SZW", "XVI": "VWS", "XVII": "BHO", "XX": "AM", "XXII": "VRO", "XXIII": "KGG"}
VERSLAG = []

def log(*a):
    t = " ".join(str(x) for x in a)
    print(t, flush=True)
    VERSLAG.append(t)

# ---------------------------------------------------------------- ophalen
def http_get(url, pad=None, pogingen=3):
    laatste = None
    for p in range(pogingen):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ken-je-partij-update/1.0 (open data, nachtelijke controle)"})
            with urllib.request.urlopen(req, timeout=180) as r:
                data = r.read()
            if pad:
                open(pad, "wb").write(data)
            return data
        except Exception as e:
            laatste = e
            time.sleep(3 * (p + 1))
    raise RuntimeError("ophalen mislukt: %s (%s)" % (url[:120], laatste))

def d_iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%S").replace(":", "%3A") + "Z"

SELECT = ("&$count=true&$top=250&$select=Nummer,Onderwerp,Titel,GestartOp,Volgnummer,Kabinetsappreciatie"
          "&$expand=Kamerstukdossier($select=Nummer,Toevoeging,Titel),Document($select=Id,Soort,DocumentNummer),"
          "Besluit($select=BesluitSoort;$expand=Stemming($select=Soort,ActorFractie,FractieGrootte)),"
          "Agendapunt($select=Id;$expand=Activiteit($select=Soort,Datum))")

def haal_zaken(van, tot):
    zaken, mislukt = {}, []
    a = van
    while a < tot:
        b = min(a + datetime.timedelta(days=1), tot)
        url0 = (BASIS + "Zaak?$filter=Soort%20eq%20%27Motie%27%20and%20Verwijderd%20eq%20false%20and%20GestartOp%20ge%20" + d_iso(a)
                + "%20and%20GestartOp%20lt%20" + d_iso(b) + SELECT)
        try:
            tekst = http_get(url0).decode("utf-8")
            m = re.search(r'"@odata.count":\s*(\d+)', tekst)
            totaal = int(m.group(1)) if m else 0
            data = json.loads(tekst)["value"]
            skip = 250
            while skip < totaal:
                data += json.loads(http_get(url0 + "&$skip=%d" % skip).decode("utf-8"))["value"]
                skip += 250
            if len(data) != totaal:
                raise RuntimeError("aantal klopt niet: %d van %d" % (len(data), totaal))
            for z in data:
                zaken[z["Nummer"]] = z
        except Exception as e:
            mislukt.append(a.strftime("%Y-%m-%d") + " (" + str(e)[:80] + ")")
        time.sleep(0.3)
        a = b
    return zaken, mislukt

def haal_zaken_map(map_):
    zaken = {}
    for f in sorted(glob.glob(os.path.join(map_, "blok_*.json"))):
        for z in json.load(open(f, encoding="utf-8"))["value"]:
            zaken[z["Nummer"]] = z
    return zaken, []

def haal_pdf(doc_id, pad):
    data = http_get(BASIS + "Document(%s)/resource" % doc_id, pad)
    return data[:4] == b"%PDF" and len(data) > 1000

# ---------------------------------------------------------------- hulpfuncties
def motie_id(z):
    if not z.get("Kamerstukdossier"):
        return None
    k = z["Kamerstukdossier"][0]
    return "%s%s-%s" % (k["Nummer"], ("-" + str(k["Toevoeging"])) if k["Toevoeging"] else "", z["Volgnummer"])

def nl_datum(iso):
    j, m, d = iso[:10].split("-")
    return "%d %s %s" % (int(d), MAANDEN[int(m) - 1], j)

def parse_nl_datum(t):
    m = re.match(r"(\d+) (\w+) (\d{4})", t or "")
    if not m or m.group(2) not in MAANDEN:
        return None
    return datetime.date(int(m.group(3)), MAANDEN.index(m.group(2)) + 1, int(m.group(1)))

def uitslag(z):
    st = [x for b in z["Besluit"] for x in b["Stemming"]]
    soort = [b["BesluitSoort"] for b in z["Besluit"] if b["Stemming"]][0].lower()
    if len(st) == 17:
        v = sum(x["FractieGrootte"] for x in st if x["Soort"] == "Voor")
        t = sum(x["FractieGrootte"] for x in st if x["Soort"] == "Tegen")
    else:   # hoofdelijke stemming: elke stem is een persoon
        v = sum(1 for x in st if x["Soort"] == "Voor")
        t = sum(1 for x in st if x["Soort"] == "Tegen")
    u = "niet aangenomen" if "niet aangenomen" in soort else "aangenomen" if "aangenomen" in soort else "verworpen"
    if (u == "aangenomen") != (v > t):
        return None
    return [u, v, t]

# ---------------------------------------------------------------- tekst uit de PDF
OPEN = re.compile(r'^(voorts overwegende|voorts constaterende|verder constaterende|verder overwegende|constaterende|overwegende|verzoekt|spreekt|zegt|van oordeel|van mening|gelet op|rekening houdend|waarschuwt|keurt|draagt|betreurt|herinnerende|vraagt|stelt vast|constateerde|roept|erkennende|constaterend|overwegend)\b', re.I)
BUL = re.compile(r'^([•–—]|-(?=\s))\s*')
FOOT = re.compile(r"^(kst-\S+|ISSN .*|’s-Gravenhage \d{4}|Tweede Kamer, vergaderjaar .*|\d{1,2})$")
EXC = ('en', 'of', 'dan', 'tot', 'als', 'met', 'te', 'c.q.', 'c.q', 'c.s.', 'respectievelijk', 'dat', 'het', 'de', 'voor', 'op', 'in')

def pdf_tekst(pad):
    return subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", pad, "-"], capture_output=True, text=True).stdout

def clean_lines(t):
    t = t.replace("\f", "\n")
    L = [re.sub(r"\s{2,}", " ", x.strip()) for x in t.split("\n")]
    L = [re.sub(r"^(De Kamer,?)\s+\S{1,2}$", r"\1", x) for x in L]          # losse tekens uit de lay-out
    L = [x for x in L if not re.fullmatch(r"[^\x00-\x7F]", x)]
    L = [x for x in L if x and not FOOT.match(x) and not re.search(r"Gravenhage \d{4}|Tweede Kamer, vergaderjaar|^kst-|^ISSN", x)]
    out, i = [], 0
    while i < len(L):
        if L[i] in ("•", "–", "—", "-") and i + 1 < len(L):
            out.append(L[i] + " " + L[i + 1]); i += 2
        else:
            out.append(L[i]); i += 1
    return out

def maak_corpus(teksten, extra_tekst=""):
    words, hard = collections.Counter(), collections.Counter()
    for t in list(teksten) + [extra_tekst]:
        for w in re.findall(r"[A-Za-zÀ-ÿ]+", t):
            words[w.lower()] += 1
        for ln in t.split("\n"):
            s = ln.strip()
            for m in re.finditer(r"[A-Za-zÀ-ÿ0-9]+-[A-Za-zÀ-ÿ0-9]+", s):
                if m.end() < len(s):
                    hard[m.group(0).lower()] += 1
    return words, hard

def parse_dictum(mid, t, corpus):
    words, HARD = corpus
    L = clean_lines(t)
    full = " ".join(L)
    ms = re.search(r"\bDe Kamer,?(?=\s+(?:gehoord|constaterende|overwegende|verzoekt|spreekt|van mening|van oordeel|roept|gelet|gezien|erkennende|voorts|verder|zegt|rekening))", full)
    me = re.search(r"\ben gaat over tot de orde van de dag[.,]?", full, re.I)
    if not ms or not me:
        return None, "geen herkenbaar begin of slot in de PDF"
    acc, start = "", None
    for idx, l in enumerate(L):
        acc += (" " if acc else "") + l
        if start is None and ms.end() <= len(acc):
            start = idx + 1
            break
    body = L[start:]
    j = " \n".join(body)
    j = re.sub(r"\s*\ben\s+gaat\s+over\s+tot\s+de\s+orde\s+van\s+de\s*\n?\s*dag.*$", "", j, flags=re.I | re.S)
    j = re.sub(r"\s*\ben gaat over tot de orde van de dag.*$", "", j, flags=re.I | re.S)
    lines = [x.strip() for x in j.split("\n") if x.strip()]
    if lines and re.match(r"^gehoord de beraadslaging,?$", lines[0], re.I):
        lines = lines[1:]
    elif lines and re.match(r"^gehoord de beraadslaging,?\s", lines[0], re.I):
        lines[0] = re.sub(r"^gehoord de beraadslaging,?\s*", "", lines[0], flags=re.I)
    paras, cur = [], ""
    def push():
        nonlocal cur
        if cur.strip():
            paras.append(cur.strip())
        cur = ""
    for l in lines:
        isb = bool(BUL.match(l))
        if not cur:
            cur = l; continue
        prev_end = cur.rstrip()[-1:]
        if isb:
            cur += "\n" + l; continue
        if prev_end == ";" or (OPEN.match(l) and prev_end in ",;."):
            push(); cur = l
        else:
            if cur.endswith("-"):
                a = re.search(r"([\wÀ-ÿ]+)-$", cur); bw = re.match(r"[\wÀ-ÿ.]+", l)
                if not a or not bw:
                    cur += l; continue
                A, B = a.group(1), bw.group(0)
                if B.lower() in EXC:
                    cur += " " + l
                elif re.fullmatch(r"[A-Z0-9]{2,}", A) or B[0].isupper() or B[0].isdigit():
                    cur += l
                elif HARD[(A + "-" + B).lower()] > 0 and not words.get((A + B).lower()):
                    cur += l
                else:
                    cur = cur[:-1] + l
            else:
                cur += " " + l
    push()
    fixed = []
    for p in paras:
        parts = p.split("\n"); out = [parts[0]]
        for q in parts[1:]:
            if BUL.match(q): out.append(q)
            else: out[-1] = out[-1] + " " + q
        fixed.append("\n".join(out))
    paras = [re.sub(r"\b([A-Z0-9]{2,})- (?!(?:en|of|dan|tot|als|met|te|c\.q)\b)(?=[a-z])", r"\1-", p) for p in fixed]
    if not paras:
        return None, "lege motietekst"
    for i, p in enumerate(paras):
        if OPEN.match(p) and p[0].isupper():
            paras[i] = p[0].lower() + p[1:]
    paras[-1] = re.sub(r"[,.;\s]+$", "", paras[-1]) + ","
    tail = " \n".join(L).replace(" \n", "\n")
    mt = re.search(r"\ben\s+gaat\s+over\s+tot\s+de\s+orde\s+van\s+de\s*\n?\s*dag[.,]?", tail, re.I)
    names = [x.strip() for x in tail[mt.end():].split("\n") if x.strip()] if mt else []
    dictum = "De Kamer,\n\ngehoord de beraadslaging,\n\n" + "\n\n".join(paras) + "\n\nen gaat over tot de orde van de dag."
    return (dictum, names), None

# ---------------------------------------------------------------- de app lezen en schrijven
def lees_app(html):
    m = re.search(r"const MOTIES=\[\n(.*?)\n\];", html, re.S)
    ids = set(re.findall(r'"id": "([^"]+)"', m.group(1))) | set(re.findall(r'\{id:"([^"]+)"', m.group(1)))
    cats = json.loads(re.search(r"^const CATS=(\{.*\});$", html, re.M).group(1))
    mn = json.loads(re.search(r"^const MIN=(\{.*\});$", html, re.M).group(1))
    partijen = json.loads(re.search(r"const PARTIJEN=(\[.*?\]);", html).group(1))
    return m, ids, cats, mn, partijen

def schrijf_app(html, m, rijen_json, cats, mn, bijgewerkt):
    body = m.group(1).rstrip().rstrip(",") + (",\n" + ",\n".join(rijen_json) if rijen_json else "")
    html = html[:m.start(1)] + body + html[m.end(1):]
    html = re.sub(r"^const CATS=.*;$", lambda _: "const CATS=" + json.dumps(cats, ensure_ascii=False) + ";", html, count=1, flags=re.M)
    html = re.sub(r"^const MIN=.*;$", lambda _: "const MIN=" + json.dumps(mn, ensure_ascii=False) + ";", html, count=1, flags=re.M)
    html = re.sub(r'const BIJGEWERKT="[^"]*"', 'const BIJGEWERKT="%s"' % bijgewerkt, html, count=1)
    return html

def dossier_naam(nummer, toevoeging, titel):
    n = str(nummer); num = n[:-3] + " " + n[-3:] if len(n) > 3 else n
    if toevoeging:
        t = str(toevoeging); num += ("-" + t) if t.isdigit() else (" " + t)
    return num + " " + (titel or "")

def groep_voor(sleutel, toevoeging, titel, mn):
    if sleutel in mn:
        return mn[sleutel], False
    t = str(toevoeging or "")
    if t and re.fullmatch(r"[A-Z]{1,5}", t) and t in BEG and re.search(r"begroting|jaarverslag|slotwet|Ministerie van|Nota over de toestand", titel or "", re.I):
        return BEG[t], False
    return "OVR", True     # nog niet ingedeeld: komt onder "Overig" en in het verslag

# ---------------------------------------------------------------- hoofdprogramma
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", default="docs/index.html")
    ap.add_argument("--dagen", type=int, default=45, help="hoeveel dagen terug opnieuw kijken")
    ap.add_argument("--diep", action="store_true", help="alles sinds 23 februari 2026 opnieuw bekijken")
    ap.add_argument("--bron-map", help="(test) lees blok_*.json uit deze map in plaats van het internet")
    ap.add_argument("--pdf-map", help="(test) lees <motie-id>.pdf uit deze map in plaats van het internet")
    ap.add_argument("--verslag", default="verslag-laatste-run.md")
    args = ap.parse_args()

    nu = datetime.datetime.utcnow()
    tot = datetime.datetime(nu.year, nu.month, nu.day, 22, 0, 0) + datetime.timedelta(days=1 if nu.hour >= 22 else 0)
    van = STARTDATUM if args.diep else max(STARTDATUM, tot - datetime.timedelta(days=args.dagen))
    log("# Verslag nachtelijke update"); log("")
    log("Gedraaid op: %s UTC, periode (indiening): %s t/m %s%s" % (nu.strftime("%Y-%m-%d %H:%M"), van.strftime("%Y-%m-%d"), tot.strftime("%Y-%m-%d"), " (diepe controle)" if args.diep else ""))

    html = open(args.app, encoding="utf-8").read()
    m, bestaand, cats, mn, PARTIJEN = lees_app(html)
    log("In de app: %d moties" % len(bestaand))

    zaken, mislukt = haal_zaken_map(args.bron_map) if args.bron_map else haal_zaken(van, tot)
    if mislukt:
        log(""); log("**Dagen die niet zijn opgehaald:** " + "; ".join(mislukt))
    log("Opgehaald: %d moties (met of zonder uitslag)" % len(zaken))
    if not zaken and not args.bron_map:
        log("Niets opgehaald: de app blijft ongewijzigd."); sys.exit(2 if mislukt else 0)

    kandidaten = {}
    for z in zaken.values():
        if not any(b["Stemming"] for b in z["Besluit"]): continue
        mid = motie_id(z)
        if mid and mid not in bestaand:
            kandidaten[mid] = z
    log("Nieuw met uitslag: %d" % len(kandidaten))

    weggelaten = []
    pdfdir = tempfile.mkdtemp(prefix="pdf_")
    teksten = {}
    for mid, z in sorted(kandidaten.items()):
        docs = [d for d in z["Document"] if str(d["Soort"]).startswith("Motie")]
        if len(docs) != 1:
            weggelaten.append((mid, "geen eenduidig motiedocument (%d gevonden)" % len(docs))); continue
        pad = os.path.join(pdfdir, mid + ".pdf")
        try:
            if args.pdf_map:
                bron = os.path.join(args.pdf_map, mid + ".pdf")
                if not os.path.exists(bron):
                    weggelaten.append((mid, "PDF niet beschikbaar")); continue
                pad = bron
            else:
                if not haal_pdf(docs[0]["Id"], pad):
                    weggelaten.append((mid, "download is geen geldige PDF")); continue
                time.sleep(0.3)
            teksten[mid] = pdf_tekst(pad)
        except Exception as e:
            weggelaten.append((mid, "PDF ophalen mislukt: " + str(e)[:80]))

    corpus = maak_corpus(teksten.values(), " ".join(re.findall(r'"dictum": "(.*?)",\s*"indiener"', m.group(1), re.S))[:3000000].replace("\\n", "\n"))
    rijen, nieuwe_dossiers, tel_stemdatum = [], {}, []
    for mid, t in teksten.items():
        z = kandidaten[mid]
        st = [s for b in z["Besluit"] for s in b["Stemming"]]
        hoofdelijk = len(st) != 17
        uit = uitslag(z)
        if uit is None:
            weggelaten.append((mid, "uitslag klopt niet met de stemmen (de bron is tegenstrijdig)")); continue
        agg = collections.defaultdict(set)
        for s in st: agg[ALIAS.get(s["ActorFractie"], s["ActorFractie"])].add(s["Soort"])
        if sorted(agg) != sorted(PARTIJEN):
            weggelaten.append((mid, "andere fracties dan de app kent: %s" % sorted(set(agg) ^ set(PARTIJEN)))); continue
        sv, fout = {}, None
        for p, v in agg.items():
            aanw = v - {"Niet deelgenomen"}
            if len(aanw) > 1: fout = "fractie %s stemde verdeeld (hoofdelijk), handmatig bepalen" % p; break
            sv[p] = {"Voor": "v", "Tegen": "t"}[list(aanw)[0]] if aanw else "n"
        if fout: weggelaten.append((mid, fout)); continue
        res, reden = parse_dictum(mid, t, corpus)
        if not res: weggelaten.append((mid, reden)); continue
        dictum, namen = res
        if re.search(r"kst-|ISSN|Voorgesteld|vergaderjaar|Gravenhage|\f", dictum) or dictum.count("en gaat over tot de orde van de dag") != 1:
            weggelaten.append((mid, "tekst bevat restanten van de PDF-opmaak")); continue
        mm = re.match(r"(?:Gewijzigde )?motie van (?:het lid|de leden) (.+?) over (.+)$", z["Onderwerp"].strip(), re.S)
        if mm and "c.s." not in mm.group(1):
            indiener, onderwerp = mm.group(1).strip(), mm.group(2).strip()
        else:
            m2 = re.search(r" over (.+)$", z["Onderwerp"].strip(), re.S)
            onderwerp = m2.group(1).strip() if m2 else z["Onderwerp"]
            indiener = (", ".join(namen[:-1]) + " en " + namen[-1]) if len(namen) > 1 else (namen[0] if namen else "")
        if not indiener or len(indiener) > 150 or re.search(r"\d|Nr\.|Gravenhage", indiener):
            weggelaten.append((mid, "indiener niet betrouwbaar te bepalen: " + indiener[:60])); continue
        onderwerp = re.sub(r"\s*\([^)]*\d[^)]*\)\s*$", "", onderwerp).strip()
        k = z["Kamerstukdossier"][0]
        vd = sorted({a["Activiteit"]["Datum"][:10] for a in z["Agendapunt"] if a.get("Activiteit") and a["Activiteit"]["Soort"] == "Stemmingen"})
        doc = [d for d in z["Document"] if str(d["Soort"]).startswith("Motie")][0]
        stem = "".join(sv[p] for p in PARTIJEN)
        sleutel = re.sub(r"-\d+$", "", mid)
        if sleutel not in cats:
            cats[sleutel] = dossier_naam(k["Nummer"], k["Toevoeging"], k["Titel"])
            g, onbekend = groep_voor(sleutel, k["Toevoeging"], k["Titel"], mn)
            mn[sleutel] = g
            if onbekend: nieuwe_dossiers[sleutel] = cats[sleutel]
        rijen.append(dict(id=mid, onderwerp=onderwerp, titel=k["Titel"] or z["Titel"], dictum=dictum, indiener=indiener,
                          datum=nl_datum(vd[0]) if len(vd) == 1 else "",
                          url="https://www.tweedekamer.nl/kamerstukken/moties/detail?id=%s&did=%s" % (z["Nummer"], doc["DocumentNummer"]),
                          oordeel=z["Kabinetsappreciatie"], stemverklaring=None, stem=stem, uitslag=uit))
        if vd: tel_stemdatum.append(vd[-1])

    bijgewerkt = re.search(r'const BIJGEWERKT="([^"]*)"', html).group(1)
    if tel_stemdatum:
        nieuw = max(tel_stemdatum); oud = parse_nl_datum(bijgewerkt)
        if not oud or datetime.date.fromisoformat(nieuw) > oud:
            bijgewerkt = nl_datum(nieuw)

    log(""); log("## Resultaat")
    log("Toegevoegd aan de app: **%d** moties" % len(rijen))
    log("Weggelaten voor controle: **%d**" % len(weggelaten))
    for mid, reden in weggelaten: log("- %s: %s" % (mid, reden))
    if nieuwe_dossiers:
        log(""); log("**Nieuwe dossiers zonder ministerie (staan onder 'Overig', graag indelen):**")
        for k_, n_ in nieuwe_dossiers.items(): log("- %s: %s" % (k_, n_))
    nieuw_html = schrijf_app(html, m, [json.dumps(r, ensure_ascii=False) for r in rijen], cats, mn, bijgewerkt)
    if rijen or nieuw_html != html:
        open(args.app, "w", encoding="utf-8").write(nieuw_html)
    open(args.verslag, "w", encoding="utf-8").write("\n".join(VERSLAG) + "\n")

if __name__ == "__main__":
    main()
