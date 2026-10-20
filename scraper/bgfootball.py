"""Second source: bulgarian-football.com (data from official BFU match reports).

Used to
  * cross-check which squad players are Bulgarian (and find ones Transfermarkt misses),
  * add the player's "първи клуб" (first registered club) as academy evidence,
  * cross-check First League stats.
"""
import re

from bs4 import BeautifulSoup

BF = "https://bulgarian-football.com"

# Transfermarkt club id -> bulgarian-football.com club slug
CLUB_SLUGS = {
    156: "Levski(Sofia)",
    31614: "Ludogorets1945(Razgrad)",
    208: "CSKA(Sofia)",
    61955: "FKCSKA1948(Sofia)",
    2531: "Botev(Plovdiv)",
    40604: "Arda1924(Kardzhali)",
    730: "LokomotivSofia1929(Sofia)",
    2259: "Lokomotiv1926(Plovdiv)",
    675: "Slavia1913(Sofia)",
    967: "Chernomore(Varna)",
    9599: "Spartak1918(Varna)",
    26462: "Botev(Vratsa)",
    19780: "DunavotRuse(Ruse)",
    40416: "Septemvri(Sofia)",
}

# bulgarian-football slug -> name that normalize_academy() understands
SLUG_NAMES = {
    "Chernomore(Varna)": "Cherno More Varna",
    "FKCSKA1948(Sofia)": "CSKA 1948",
    "DunavotRuse(Ruse)": "Dunav Ruse",
    "LokomotivSofia1929(Sofia)": "Lokomotiv Sofia",
    "Chernomorets1919(Burgas)": "Chernomorets Burgas",
    "Pirin22(Blagoevgrad)": "Pirin Blagoevgrad",
}

LEAGUE = "Първа професионална лига"
EUROPE = ("Шампионска лига", "Лига Европа", "Лига на конференциите")


def competition_category(name):
    """Map a bulgarian-football competition name to league/cup/supercup/europe."""
    if name == LEAGUE:
        return "league"
    if name == "Купа на България":
        return "cup"
    if name == "Суперкупа на България":
        return "supercup"
    if any(e in name for e in EUROPE):  # includes "Бараж за ..." qualifiers
        return "europe"
    return None

_TR = dict(zip("абвгдежзийклмнопрстуфхцчшщъьюяѝ",
               ["a", "b", "v", "g", "d", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r",
                "s", "t", "u", "f", "h", "ts", "ch", "sh", "sht", "a", "y", "yu", "ya", "i"]))


def translit(s):
    """Bulgarian Cyrillic -> Latin (streamlined system), lower-case."""
    return "".join(_TR.get(c, c) for c in (s or "").lower())


_TO_BG = [("sht", "щ"), ("zh", "ж"), ("ts", "ц"), ("ch", "ч"), ("sh", "ш"), ("yu", "ю"),
          ("ya", "я"), ("a", "а"), ("b", "б"), ("v", "в"), ("w", "в"), ("g", "г"), ("d", "д"),
          ("e", "е"), ("z", "з"), ("i", "и"), ("y", "й"), ("k", "к"), ("c", "к"), ("q", "к"),
          ("x", "кс"), ("l", "л"), ("m", "м"), ("n", "н"), ("o", "о"), ("p", "п"), ("r", "р"),
          ("s", "с"), ("t", "т"), ("u", "у"), ("f", "ф"), ("h", "х")]


# Common names where the Latin 'a' stands for 'ъ'.
_TO_BG_WORDS = {"aleksandar": "Александър", "dimitar": "Димитър", "petar": "Петър",
                "kalin": "Калин", "valkov": "Вълков", "valchev": "Вълчев"}


def to_cyrillic(name):
    """Approximate Latin -> Bulgarian Cyrillic for names with no Cyrillic source.

    Reverses the streamlined transliteration; it cannot recover 'ъ' (written 'a'),
    so callers mark the result as approximate.
    """
    out = []
    for word in (name or "").split():
        if word.lower() in _TO_BG_WORDS:
            out.append(_TO_BG_WORDS[word.lower()])
            continue
        w, res, i = word.lower(), "", 0
        while i < len(w):
            for lat, cyr in _TO_BG:
                if w.startswith(lat, i):
                    res += cyr
                    i += len(lat)
                    break
            else:
                res += w[i]
                i += 1
        out.append(res[:1].upper() + res[1:])
    return " ".join(out) or None


def name_key(s):
    """Loose comparison key: latin, letters only, common spelling variants folded."""
    k = translit(s)
    k = re.sub(r"[^a-z ]", "", k.replace("-", " "))
    for a, b in (("iy", "i"), ("yy", "y"), ("ia", "ya"), ("io", "yo"), ("j", "y"), ("w", "v"),
                 ("ck", "k"), ("x", "ks"), ("th", "t"), ("ph", "f"), ("ou", "u")):
        k = k.replace(a, b)
    return k.split()


def slug_to_name(slug):
    if slug in SLUG_NAMES:
        return SLUG_NAMES[slug]
    m = re.match(r"([^(]+)\(([^)]*)\)", slug)
    if not m:
        return slug
    base = re.sub(r"\d+", "", m.group(1))
    base = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", base).strip()
    city = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", m.group(2))
    return base if city.lower() in base.lower() else f"{base} {city}"


def _text(el):
    return " ".join(el.get_text(" ", strip=True).split()) if el else ""


def _date(s):
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", s or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def _int(s):
    s = (s or "").strip()
    return int(s) if s.isdigit() else 0


def club_slug_from_href(href):
    m = re.search(r"/clubs/([^/]+)", href or "")
    return m.group(1) if m else None


def parse_club_players(html):
    """Season roster page -> [(player_slug, display_name)]."""
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    for a in soup.select("tr.stats td a[href*='/players/']"):
        slug = a["href"].rstrip("/").rsplit("/", 1)[-1]
        if slug not in seen:
            seen.add(slug)
            out.append((slug, _text(a)))
    return out


def parse_club_name(html):
    """Cyrillic club name from a club page title: 'Черно море (Варна) | bulgarian-football.com'."""
    soup = BeautifulSoup(html, "lxml")
    title = _text(soup.title) if soup.title else ""
    return title.split("|")[0].strip() or None


def parse_player(html, season_label):
    soup = BeautifulSoup(html, "lxml")
    details = {}
    for block in soup.select(".info .details > div"):
        label = _text(block.select_one(".label"))
        val = block.select_one(".value")
        if label and val:
            details[label] = {"text": _text(val),
                              "flags": [f.get("title") for f in val.select(".flag[title]")],
                              "href": (val.find("a") or {}).get("href") if val.find("a") else None}

    transfers = []
    for tr in soup.select("#transfers tbody tr"):
        tds = tr.find_all("td")
        if len(tds) < 5:
            continue
        transfers.append({
            "left": _date(_text(tds[0])),
            "from": club_slug_from_href((tds[1].find("a") or {}).get("href") if tds[1].find("a") else None),
            "type": _text(tds[2]),
            "joined": _date(_text(tds[3])),
            "to": club_slug_from_href((tds[4].find("a") or {}).get("href") if tds[4].find("a") else None),
            "to_name": _text(tds[4]),
        })
    first = next((t for t in transfers if t["type"] == "първи клуб"), None)

    comps = {}
    for tr in soup.select("#stats-0 table tbody tr"):
        v = [_text(td) for td in tr.find_all("td")]
        if len(v) < 15 or v[0] != season_label:
            continue
        cat = competition_category(v[2].rstrip(" *"))
        if not cat:
            continue  # reserve-team leagues, friendlies etc.
        # A player can appear for two clubs in one season - sum them.
        for bucket in (cat, "total"):
            acc = comps.setdefault(bucket, {})
            for k, i in (("appearances", 3), ("minutes", 4), ("starts", 5), ("sub_on", 6),
                         ("sub_off", 7), ("goals", 9), ("yellow", 12), ("second_yellow", 13),
                         ("red", 14)):
                acc[k] = acc.get(k, 0) + _int(v[i])
    league = comps.get("league", {})

    birth = details.get("МЯСТО НА РАЖДАНЕ", {})
    return {
        "full_name": _text(soup.select_one("h1.names")),
        "nationalities": details.get("НАЦИОНАЛНОСТ", {}).get("flags") or [],
        "dob": _date(details.get("ДАТА НА РАЖДАНЕ", {}).get("text")),
        "birth_place": birth.get("text"),
        "birth_country": (birth.get("flags") or [None])[0],
        "position": details.get("ПОЗИЦИЯ", {}).get("text"),
        "current_club": club_slug_from_href(details.get("НАСТОЯЩ ОТБОР", {}).get("href")),
        "first_club": first["to"] if first else None,
        "first_club_name": first["to_name"] if first else None,
        "first_club_date": first["joined"] if first else None,
        "transfers": transfers,
        "league": league,
        "comps": comps,
    }


def match_player(bf, tm_players, name_fallback=True):
    """Find the Transfermarkt player matching a bulgarian-football player.

    Returns (player, how): how is "dob" (same DOB + shared name token), "dob_only"
    (DOB unique in the squad) or "name" (first + last name agree, DOB differs or is
    missing - the sources sometimes disagree on DOB by a day or more).
    """
    bf_tokens = set(name_key(bf["full_name"]))
    same_dob = [p for p in tm_players if bf["dob"] and p["dob"] == bf["dob"]]
    for p in same_dob:
        tm_tokens = set(name_key(p["name"])) | set(name_key(p.get("full_name") or ""))
        if bf_tokens & tm_tokens:
            return p, "dob"
    if len(same_dob) == 1:
        return same_dob[0], "dob_only"
    if name_fallback:
        hits = []
        for p in tm_players:
            tm_tokens = name_key(p["name"])
            if len(tm_tokens) >= 2 and tm_tokens[0] in bf_tokens and tm_tokens[-1] in bf_tokens:
                hits.append(p)
        if len(hits) == 1:
            return hits[0], "name"
    return None, None
