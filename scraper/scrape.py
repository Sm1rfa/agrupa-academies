"""Scrape efbet League squads, Bulgarian players, youth clubs and season stats
from Transfermarkt into a local SQLite database.

Usage:
    python scraper/scrape.py                 # season 2026 (= 2026/27)
    python scraper/scrape.py --season 2026 --refresh

HTML responses are cached in scraper/cache/ so re-runs are cheap; use
--refresh to re-download squad/stats pages (profiles stay cached for 7 days).
"""
import argparse
import hashlib
import json
import zlib
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from academies import ACADEMY_BG, normalize_academy
import bgfootball as bf

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(__file__).resolve().parent / "cache"
DB_PATH = ROOT / "data" / "youth.sqlite"
BASE = "https://www.transfermarkt.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
DELAY = 2.5  # seconds between live requests - be polite
PROFILE_MAX_AGE = 7 * 24 * 3600  # biography pages (youth clubs) change rarely
STATS_MAX_AGE = 12 * 3600        # squads, stats, BFU player pages (they carry stats)

session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
_last_request = 0.0
# Oldest page timestamp used per data source - shown on the site as "data as of".
data_as_of = {}


def fetch(path, max_age=None, source=None):
    """GET a page, using the on-disk cache when younger than max_age seconds.

    `source` ("tm"/"bf") records the page's age in data_as_of.
    """
    global _last_request
    CACHE.mkdir(exist_ok=True)
    f = CACHE / (hashlib.md5(path.encode()).hexdigest() + ".html")
    if f.exists() and (max_age is None or time.time() - f.stat().st_mtime < max_age):
        if source:
            data_as_of[source] = min(data_as_of.get(source, time.time()), f.stat().st_mtime)
        return f.read_text(encoding="utf-8")
    if source:
        data_as_of[source] = min(data_as_of.get(source, time.time()), time.time())
    wait = DELAY - (time.time() - _last_request)
    if wait > 0:
        time.sleep(wait)
    for attempt in range(3):
        _last_request = time.time()
        r = session.get(path if path.startswith("http") else BASE + path, timeout=30)
        if r.status_code == 200:
            f.write_text(r.text, encoding="utf-8")
            return r.text
        print(f"  ! HTTP {r.status_code} for {path}, retry {attempt + 1}", file=sys.stderr)
        time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {path}")


def text(el):
    return " ".join(el.get_text(" ", strip=True).split()) if el else ""


def to_int(s):
    s = (s or "").replace("'", "").replace(".", "").strip()
    return int(s) if s.isdigit() else 0


def parse_date(s):
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", s or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


# ---------------------------------------------------------------- parsers

def parse_league(html, season):
    soup = BeautifulSoup(html, "lxml")
    clubs = {}
    for a in soup.select("table.items td.hauptlink a[href*='/startseite/verein/']"):
        m = re.match(r"/([^/]+)/startseite/verein/(\d+)", a["href"])
        if m and m.group(2) not in clubs:
            clubs[m.group(2)] = {"tm_id": int(m.group(2)), "slug": m.group(1),
                                 "name": a.get("title") or text(a)}
    return list(clubs.values())


def parse_squad(html):
    soup = BeautifulSoup(html, "lxml")
    players = []
    for row in soup.select("table.items > tbody > tr"):
        tds = row.find_all("td", recursive=False)
        if len(tds) < 9:
            continue
        link = tds[1].select_one("td.hauptlink a[href*='/profil/spieler/']")
        if not link:
            continue
        m = re.match(r"/([^/]+)/profil/spieler/(\d+)", link["href"])
        pos_rows = tds[1].select("table.inline-table tr")
        img = tds[1].select_one("img[data-src]")
        players.append({
            "tm_id": int(m.group(2)),
            "slug": m.group(1),
            "name": text(link),
            "shirt": text(tds[0]),
            "position": text(pos_rows[1]) if len(pos_rows) > 1 else "",
            "dob": parse_date(text(tds[2])),
            "nationalities": [i.get("title") for i in tds[3].find_all("img") if i.get("title")],
            "joined": parse_date(text(tds[6])),
            "signed_from": next((i.get("title") for i in tds[7].find_all("img") if i.get("title")), None),
            "contract_until": parse_date(text(tds[8])),
            "market_value": text(tds[9]) if len(tds) > 9 else "",
            "photo": img["data-src"] if img else None,
        })
    return players


def parse_stats(html):
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table.items")
    stats = {}
    if not table:
        return stats
    for row in table.select("tbody > tr"):
        tds = row.find_all("td", recursive=False)
        link = row.select_one("td.hauptlink a[href*='/profil/spieler/']")
        if not link or len(tds) < 15:
            continue
        pid = int(re.search(r"/spieler/(\d+)", link["href"]).group(1))
        v = [text(td) for td in tds]
        stats[pid] = {
            "in_squad": to_int(v[4]), "appearances": to_int(v[5]), "goals": to_int(v[6]),
            "assists": to_int(v[7]), "yellow": to_int(v[8]), "second_yellow": to_int(v[9]),
            "red": to_int(v[10]), "sub_on": to_int(v[11]), "sub_off": to_int(v[12]),
            "minutes": to_int(v[14]),
        }
    return stats


YEAR_RANGE = re.compile(r"^\s*(\d{4})?\s*[–—-]?\s*(\d{4})?\s+(\D.*)$")


# "(2005-2009)", "(-2015)", "(-1/2016)", "(bis 4/2013)", "(2006)", "(2021-1/2022)"
YEAR_PARENS = re.compile(
    r"\s*\((?:bis|until)?\s*(?:\d{1,2}/)?(\d{4})?\s*([–—-])?\s*(?:\d{1,2}/)?(\d{4})?\s*(?:\.\.\.|…)?\)\s*$")


def parse_youth_clubs(raw):
    """'2007–2010 Litex Lovech, Levski Sofia (2010-2016); CSKA' -> list of dicts."""
    out = []
    for part in [p.strip() for p in re.split(r"[,;](?![^()]*\))", raw) if p.strip()]:
        start = end = None
        m = YEAR_RANGE.match(part) if re.match(r"^\s*(\d{4}|[–—-]\s*\d{4})", part) else None
        if m:
            start, end, name = m.group(1), m.group(2), m.group(3).strip()
        else:
            name = part
            pm = YEAR_PARENS.search(name)
            if pm and (pm.group(1) or pm.group(3)):
                first, dash, second = pm.group(1), pm.group(2), pm.group(3)
                if "bis" in pm.group(0) or "until" in pm.group(0):
                    start, end = None, first
                elif dash:
                    start, end = first, second
                else:
                    start = end = first
                name = name[:pm.start()].strip()
            else:
                # "FC Chavdar (Etropole)" -> "FC Chavdar Etropole"
                name = re.sub(r"\s*\(([^()\d]+)\)\s*$", r" \1", name).strip()
        if name:
            out.append({"raw": part, "name": name,
                        "start": int(start) if start else None,
                        "end": int(end) if end else None})
    return out


def parse_profile(html):
    soup = BeautifulSoup(html, "lxml")
    info = {}
    for lab in soup.select("span.info-table__content--regular"):
        val = lab.find_next_sibling("span")
        if val is None:
            continue
        key = text(lab).rstrip(":")
        info[key] = {"text": text(val),
                     "flags": [i.get("title") for i in val.find_all("img") if i.get("title")]}
    youth_raw = ""
    for h2 in soup.select("h2.content-box-headline"):
        if text(h2).lower() == "youth clubs":
            youth_raw = text(h2.find_next_sibling("div", class_="content"))
            break
    birth = info.get("Place of birth", {})
    club = soup.select_one(".data-header__club a")
    league = soup.select_one("a.data-header__league-link")
    level_flag = None
    for lab in soup.select(".data-header__club-info .data-header__label"):
        if "League level" in text(lab):
            img = lab.select_one("img[title]")
            level_flag = img.get("title") if img else None
    return {
        "current_club": (club.get("title") or text(club)) if club else None,
        "league": text(league) or None,
        "league_country": level_flag,
        "full_name": info.get("Name in home country", {}).get("text"),
        "birth_place": birth.get("text"),
        "birth_country": (birth.get("flags") or [None])[0],
        "citizenship": info.get("Citizenship", {}).get("flags") or [],
        "position_detail": info.get("Position", {}).get("text"),
        "foot": info.get("Foot", {}).get("text"),
        "height": info.get("Height", {}).get("text"),
        "youth_raw": youth_raw,
        "youth_clubs": parse_youth_clubs(youth_raw),
    }


# ---------------------------------------------------------------- database

SCHEMA_VERSION = "5"
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS clubs (
    tm_id INTEGER, season INTEGER, slug TEXT, name TEXT, name_bg TEXT, academy TEXT, bf_slug TEXT,
    PRIMARY KEY (tm_id, season));
CREATE TABLE IF NOT EXISTS academies (academy TEXT PRIMARY KEY, name_bg TEXT);
CREATE TABLE IF NOT EXISTS nt_teams (
    key TEXT, season INTEGER, tm_id INTEGER, slug TEXT, ord INTEGER,
    PRIMARY KEY (key, season));
CREATE TABLE IF NOT EXISTS nt_players (
    team TEXT, season INTEGER, player_id INTEGER,
    name TEXT, name_bg TEXT, name_bg_approx INTEGER, full_name TEXT, slug TEXT, shirt TEXT,
    position TEXT, dob TEXT, birth_place TEXT, birth_country TEXT, nationalities TEXT, photo TEXT,
    club TEXT, club_bg TEXT, club_id INTEGER, league TEXT, league_country TEXT,
    caps INTEGER, goals INTEGER, debut TEXT, market_value TEXT, in_league INTEGER,
    PRIMARY KEY (team, season, player_id));
CREATE TABLE IF NOT EXISTS players (
    id INTEGER, season INTEGER, club_id INTEGER,
    sources TEXT, checks TEXT, tm_id INTEGER, bf_slug TEXT,
    name TEXT, name_bg TEXT, name_bg_approx INTEGER, full_name TEXT, slug TEXT, shirt TEXT,
    position TEXT, position_detail TEXT, position_bg TEXT,
    dob TEXT, birth_place TEXT, birth_place_bg TEXT, birth_country TEXT, born_in_bulgaria INTEGER,
    nationalities TEXT, dual_national INTEGER, foot TEXT, height TEXT,
    joined TEXT, signed_from TEXT, contract_until TEXT, market_value TEXT, photo TEXT,
    youth_raw TEXT, homegrown INTEGER,
    in_squad INTEGER, appearances INTEGER, goals INTEGER, assists INTEGER,
    yellow INTEGER, second_yellow INTEGER, red INTEGER, sub_on INTEGER, sub_off INTEGER,
    minutes INTEGER,
    bf_appearances INTEGER, bf_minutes INTEGER, bf_goals INTEGER,
    bf_yellow INTEGER, bf_red INTEGER, comps TEXT,
    PRIMARY KEY (id, season));
CREATE TABLE IF NOT EXISTS youth_clubs (
    player_id INTEGER, season INTEGER, ord INTEGER, source TEXT,
    raw TEXT, name TEXT, academy TEXT, year_from INTEGER, year_to INTEGER, age_at INTEGER,
    PRIMARY KEY (player_id, season, ord));
CREATE INDEX IF NOT EXISTS idx_players_club ON players(season, club_id);
CREATE INDEX IF NOT EXISTS idx_youth_academy ON youth_clubs(season, academy);
"""

BG_NAT = {"България": "Bulgaria"}


def open_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    try:
        ver = db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    except sqlite3.OperationalError:
        ver = None
    if not ver or ver[0] != SCHEMA_VERSION:
        for t in ("meta", "clubs", "players", "youth_clubs", "academies", "nt_teams", "nt_players"):
            db.execute(f"DROP TABLE IF EXISTS {t}")
    db.executescript(SCHEMA)
    db.execute("INSERT OR REPLACE INTO meta VALUES ('schema_version', ?)", (SCHEMA_VERSION,))
    return db


def insert(db, table, row):
    cols = list(row)
    db.execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
               [row[c] for c in cols])


def bg_position(pos):
    """bulgarian-football position -> Transfermarkt-style English label."""
    p = (pos or "").lower()
    if "вратар" in p:
        return "Goalkeeper"
    if "полузащитник" in p:
        return "Midfield"
    if "защитник" in p:
        return "Defender"
    if "нападател" in p or "крило" in p:
        return "Attack"
    return pos or ""


def age_on(dob, date):
    if not dob or not date:
        return None
    y1, m1, d1 = map(int, dob.split("-"))
    y2, m2, d2 = map(int, date.split("-"))
    return y2 - y1 - ((m2, d2) < (m1, d1))


_CYR = re.compile("[а-яА-Я]")


def cyrillic(*names):
    """First candidate written in Cyrillic, or None."""
    return next((n for n in names if n and _CYR.search(n)), None)


def short_name(full):
    """'Георги Георгиев Венциславов' -> 'Георги Венциславов' (drop the patronymic)."""
    parts = (full or "").split()
    return f"{parts[0]} {parts[-1]}" if len(parts) >= 3 else (full or None)


def synthetic_id(bf_slug):
    """Stable negative id for players only bulgarian-football.com knows about."""
    return -(zlib.crc32(bf_slug.encode()) & 0x7FFFFFFF)


def scrape_bf_club(club_id, season, page_age, squad):
    """Return ({tm_id: bf_data}, [unmatched Bulgarians], roster_size, Cyrillic club name)."""
    slug = bf.CLUB_SLUGS.get(club_id)
    if not slug:
        return {}, [], 0, None
    label = f"{season}/{season + 1}"
    html = fetch(f"{bf.BF}/clubs/{slug}/players/season:{season}-{season + 1}", page_age, "bf")
    roster = bf.parse_club_players(html)
    matched, unmatched = {}, []
    for pslug, _ in roster:
        d = bf.parse_player(fetch(f"{bf.BF}/players/{pslug}", page_age, "bf"), label)
        d["slug"] = pslug
        # Match first: loanees show their parent club as "current club" on bulgarian-football.
        m, how = bf.match_player(d, squad)
        if m:
            d["match"] = how
            matched[m["tm_id"]] = d
        elif d["current_club"] and d["current_club"] != slug:
            continue  # left the club during the season
        elif "България" in d["nationalities"]:
            unmatched.append(d)
    return matched, unmatched, len(roster), bf.parse_club_name(html)


def youth_rows(prof, bfd, dob):
    rows = []
    for y in (prof or {}).get("youth_clubs", []):
        rows.append({"source": "tm", "raw": y["raw"], "name": y["name"],
                     "academy": normalize_academy(y["name"]),
                     "year_from": y["start"], "year_to": y["end"], "age_at": None})
    if bfd and bfd.get("first_club"):
        name = bf.slug_to_name(bfd["first_club"])
        date = bfd["first_club_date"]
        rows.append({"source": "bf", "raw": bfd["first_club_name"], "name": name,
                     "academy": normalize_academy(name),
                     "year_from": int(date[:4]) if date else None, "year_to": None,
                     "age_at": age_on(dob or bfd.get("dob"), date)})
    return rows


def stat_cols(tm, bf_league, has_bf):
    """Season stat columns: Transfermarkt numbers plus bulgarian-football's for comparison."""
    lg = bf_league or {}
    return {
        "in_squad": tm.get("in_squad"), "appearances": tm.get("appearances", 0),
        "goals": tm.get("goals", 0), "assists": tm.get("assists", 0),
        "yellow": tm.get("yellow", 0), "second_yellow": tm.get("second_yellow", 0),
        "red": tm.get("red", 0), "sub_on": tm.get("sub_on", 0),
        "sub_off": tm.get("sub_off", 0), "minutes": tm.get("minutes", 0),
        "bf_appearances": lg.get("appearances", 0) if has_bf else None,
        "bf_minutes": lg.get("minutes", 0) if has_bf else None,
        "bf_goals": lg.get("goals", 0) if has_bf else None,
        "bf_yellow": lg.get("yellow", 0) if has_bf else None,
        "bf_red": lg.get("red", 0) + lg.get("second_yellow", 0) if has_bf else None,
    }


# National teams on Transfermarkt: (key, club id, slug). The squad page lists the most
# recent call-ups with current club, caps, goals and debut.
NATIONAL_TEAMS = [
    ("A", 3394, "bulgarien"),
    ("U21", 21361, "bulgarien-u21"),
    ("U19", 27256, "bulgarien-u19"),
    ("U17", 35746, "bulgarien-u17"),
]
# Youth sides: "Levski Sofia U17", "CD Lugo Youth", "CSKA Sofia III" (CSKA's youth-age third team)
YOUTH_TEAM = re.compile(r"\b(U\s?-?1[5-9]|U\s?-?2[0-3]|Youth|Juniors?|Yth\.?|III)\b", re.IGNORECASE)


def parse_nt_squad(html):
    soup = BeautifulSoup(html, "lxml")
    out = []
    for row in soup.select("table.items > tbody > tr"):
        tds = row.find_all("td", recursive=False)
        link = row.select_one("td.hauptlink a[href*='/profil/spieler/']")
        if not link or len(tds) < 10:
            continue
        m = re.match(r"/([^/]+)/profil/spieler/(\d+)", link["href"])
        pos_rows = tds[1].select("table.inline-table tr")
        club_a = tds[3].find("a", href=re.compile(r"/verein/\d+"))
        club_img = tds[3].find("img", title=True)
        img = tds[1].select_one("img[data-src]")
        out.append({
            "tm_id": int(m.group(2)), "slug": m.group(1), "name": text(link),
            "shirt": text(tds[0]),
            "position": text(pos_rows[1]) if len(pos_rows) > 1 else "",
            "dob": parse_date(text(tds[2])),
            "club": (club_img.get("title") if club_img else None) or text(tds[3]) or None,
            "club_id": int(re.search(r"/verein/(\d+)", club_a["href"]).group(1)) if club_a else None,
            "caps": to_int(text(tds[6])), "goals": to_int(text(tds[7])),
            "debut": parse_date(text(tds[8])), "market_value": text(tds[9]),
            "photo": img["data-src"] if img else None,
        })
    return out


def scrape_national_teams(db, season, page_age):
    db.execute("DELETE FROM nt_teams WHERE season=?", (season,))
    db.execute("DELETE FROM nt_players WHERE season=?", (season,))
    league_rows = {r[0]: r[1:] for r in db.execute(
        "SELECT id, name_bg, full_name FROM players WHERE season=?", (season,))}
    for ord_, (key, tm_id, slug) in enumerate(NATIONAL_TEAMS):
        squad = parse_nt_squad(fetch(f"/{slug}/kader/verein/{tm_id}/saison_id/{season}/plus/1",
                                     page_age, "tm"))
        insert(db, "nt_teams", {"key": key, "season": season, "tm_id": tm_id, "slug": slug,
                                "ord": ord_})
        print(f"  National team {key}: {len(squad)} players")
        for p in squad:
            prof = parse_profile(fetch(f"/{p['slug']}/profil/spieler/{p['tm_id']}", PROFILE_MAX_AGE))
            in_league = p["tm_id"] in league_rows
            full_bg = cyrillic(league_rows[p["tm_id"]][1] if in_league else None, prof["full_name"])
            nats = prof["citizenship"]
            club = p["club"] or prof["current_club"] or ""
            # Youth-team profiles have no league header; a known Bulgarian academy
            # means the club is in Bulgaria.
            club_base_bg = ACADEMY_BG.get(normalize_academy(club))
            league_country = prof["league_country"] or ("Bulgaria" if club_base_bg else None)
            team_suffix = YOUTH_TEAM.search(club)
            club_bg = f"{club_base_bg} {team_suffix.group(0)}" if club_base_bg and team_suffix \
                else club_base_bg
            insert(db, "nt_players", {
                "team": key, "season": season, "player_id": p["tm_id"],
                "name": p["name"], "name_bg": short_name(full_bg) or bf.to_cyrillic(p["name"]),
                "name_bg_approx": int(not full_bg), "full_name": full_bg,
                "slug": p["slug"], "shirt": p["shirt"], "position": p["position"], "dob": p["dob"],
                "birth_place": prof["birth_place"], "birth_country": prof["birth_country"],
                "nationalities": "|".join(nats), "photo": p["photo"],
                "club": club or None, "club_bg": club_bg, "club_id": p["club_id"],
                "league": prof["league"], "league_country": league_country,
                "caps": p["caps"], "goals": p["goals"], "debut": p["debut"],
                "market_value": p["market_value"], "in_league": int(in_league),
            })
            # League players already have academy rows (incl. BFU evidence).
            has_rows = db.execute("SELECT 1 FROM youth_clubs WHERE player_id=? AND season=?",
                                  (p["tm_id"], season)).fetchone()
            if has_rows:
                continue
            rows = youth_rows(prof, None, p["dob"])
            if YOUTH_TEAM.search(club):
                # A youth player's current club youth team is itself academy evidence.
                rows.append({"source": "club", "raw": club, "name": club,
                             "academy": normalize_academy(club), "year_from": None,
                             "year_to": None, "age_at": None})
            for i, y in enumerate(rows):
                insert(db, "youth_clubs", {"player_id": p["tm_id"], "season": season, "ord": i, **y})
        db.commit()


def fill_academy_names(db, season):
    """academies table: Bulgarian display name per academy (manual table, then BFU names)."""
    bf_names = dict(db.execute("""SELECT academy, raw FROM youth_clubs
                                  WHERE source='bf' AND season=? GROUP BY academy""", (season,)))
    for (academy,) in db.execute("SELECT DISTINCT academy FROM youth_clubs").fetchall():
        name_bg = ACADEMY_BG.get(academy) or bf_names.get(academy)
        db.execute("INSERT OR REPLACE INTO academies VALUES (?, ?)", (academy, name_bg))
    db.commit()
    missing = [a for (a,) in db.execute(
        "SELECT academy FROM academies WHERE name_bg IS NULL ORDER BY academy")]
    if missing:
        print(f"  academies without a Bulgarian name ({len(missing)}): {', '.join(missing)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026, help="start year, 2026 = 2026/27")
    ap.add_argument("--refresh", action="store_true", help="re-download league/squad/stats pages")
    ap.add_argument("--no-bf", action="store_true", help="skip the bulgarian-football.com cross-check")
    ap.add_argument("--no-nt", action="store_true", help="skip the national teams")
    args = ap.parse_args()
    season = args.season
    page_age = 0 if args.refresh else STATS_MAX_AGE

    db = open_db()
    league = fetch(f"/efbet-liga/startseite/wettbewerb/BU1/saison_id/{season}", page_age)
    clubs = parse_league(league, season)
    print(f"Season {season}/{(season + 1) % 100:02d}: {len(clubs)} clubs")
    if len(clubs) < 10:
        sys.exit("Club list looks wrong - aborting so the DB is not clobbered")

    for t in ("clubs", "players", "youth_clubs"):
        db.execute(f"DELETE FROM {t} WHERE season=?", (season,))

    squads, pending = {}, []
    for club in clubs:
        club_academy = normalize_academy(club["name"])
        squad = parse_squad(fetch(
            f"/{club['slug']}/kader/verein/{club['tm_id']}/saison_id/{season}/plus/1", page_age, "tm"))
        stats = parse_stats(fetch(
            f"/{club['slug']}/leistungsdaten/verein/{club['tm_id']}/reldata/BU1%26{season}/plus/1",
            page_age, "tm"))
        squads[club["tm_id"]] = squad
        bf_matched, bf_unmatched, bf_roster, club_bg = ({}, [], 0, None) if args.no_bf else \
            scrape_bf_club(club["tm_id"], season, page_age, squad)
        insert(db, "clubs", {"tm_id": club["tm_id"], "season": season, "slug": club["slug"],
                             "name": club["name"], "name_bg": ACADEMY_BG.get(club_academy) or club_bg,
                             "academy": club_academy, "bf_slug": bf.CLUB_SLUGS.get(club["tm_id"])})

        tm_bg = {p["tm_id"] for p in squad if "Bulgaria" in p["nationalities"]}
        bf_bg = {pid for pid, d in bf_matched.items() if "България" in d["nationalities"]}
        include = [p for p in squad if p["tm_id"] in tm_bg | bf_bg]
        print(f"  {club['name']}: TM {len(squad)} players / {len(tm_bg)} BG; "
              f"BFU roster {bf_roster} / {len(bf_bg)} BG matched, {len(bf_unmatched)} BG unmatched")

        for p in include:
            prof = parse_profile(fetch(f"/{p['slug']}/profil/spieler/{p['tm_id']}", PROFILE_MAX_AGE))
            st = stats.get(p["tm_id"], {})
            bfd = bf_matched.get(p["tm_id"])
            nats = prof["citizenship"] or p["nationalities"]
            if bfd and "Bulgaria" not in nats and "България" in bfd["nationalities"]:
                nats = ["Bulgaria"] + nats
            checks = []
            if p["tm_id"] not in tm_bg:
                checks.append("tm_not_bg")
            if not args.no_bf:
                if not bfd:
                    checks.append("bf_missing")
                else:
                    if "България" not in bfd["nationalities"]:
                        checks.append("bf_not_bg")
                    if bfd.get("match") == "name" and bfd.get("dob") and p["dob"]:
                        checks.append("dob_diff")
                    if (bfd["league"].get("appearances", 0) != st.get("appearances", 0)
                            or bfd["league"].get("goals", 0) != st.get("goals", 0)):
                        checks.append("stats_diff")
            yrows = youth_rows(prof, bfd, p["dob"])
            bfd = bfd or {}
            full_bg = cyrillic(bfd.get("full_name"), prof["full_name"])
            insert(db, "players", {
                "id": p["tm_id"], "season": season, "club_id": club["tm_id"],
                "sources": "tm+bf" if bfd else "tm", "checks": "|".join(checks),
                "tm_id": p["tm_id"], "bf_slug": bfd.get("slug"),
                "name": p["name"], "name_bg": short_name(full_bg) or bf.to_cyrillic(p["name"]),
                "name_bg_approx": int(not full_bg),
                "full_name": full_bg or prof["full_name"], "slug": p["slug"], "shirt": p["shirt"],
                "position": p["position"], "position_detail": prof["position_detail"],
                "position_bg": bfd.get("position"),
                "dob": p["dob"] or bfd.get("dob"),
                "birth_place": prof["birth_place"] or bfd.get("birth_place"),
                "birth_place_bg": cyrillic(bfd.get("birth_place")),
                "birth_country": prof["birth_country"]
                or BG_NAT.get(bfd.get("birth_country"), bfd.get("birth_country")),
                "born_in_bulgaria": None, "nationalities": "|".join(nats),
                "dual_national": int(len(nats) > 1), "foot": prof["foot"], "height": prof["height"],
                "joined": p["joined"], "signed_from": p["signed_from"],
                "contract_until": p["contract_until"], "market_value": p["market_value"],
                "photo": p["photo"], "youth_raw": prof["youth_raw"],
                "homegrown": int(club_academy in {y["academy"] for y in yrows}),
                **stat_cols(st, bfd.get("league"), bool(bfd)),
                "comps": json.dumps(bfd.get("comps")) if bfd else None,
            })
            for i, y in enumerate(yrows):
                insert(db, "youth_clubs", {"player_id": p["tm_id"], "season": season, "ord": i, **y})

        pending += [(club, club_academy, d) for d in bf_unmatched]
        db.commit()

    # Bulgarians in BFU match reports that this club's Transfermarkt squad doesn't list.
    # If Transfermarkt has them at another club (same DOB + name), flag that player
    # instead of adding a duplicate.
    for club, club_academy, d in pending:
        other = None
        for cid, sq in squads.items():
            if cid != club["tm_id"]:
                # Across clubs, a shared birth date alone is not enough (two different
                # players were once "matched" that way) - the name must agree too.
                m, how = bf.match_player(d, sq, name_fallback=False)
                if m and how == "dob":
                    other = m
                    break
        if other:
            row = db.execute("SELECT checks FROM players WHERE id=? AND season=?",
                             (other["tm_id"], season)).fetchone()
            if row is not None:
                checks = [c for c in row[0].split("|") if c and c != "bf_missing"] + ["club_diff"]
                db.execute("UPDATE players SET checks=? WHERE id=? AND season=?",
                           ("|".join(checks), other["tm_id"], season))
            continue
        pid = synthetic_id(d["slug"])
        lg = d["league"]
        nats = [BG_NAT.get(n, n) for n in d["nationalities"]]
        yrows = youth_rows(None, d, d["dob"])
        parts = d["full_name"].split()
        st = {k: lg.get(k, 0) for k in ("appearances", "goals", "yellow", "second_yellow",
                                        "red", "sub_on", "sub_off", "minutes")}
        insert(db, "players", {
            "id": pid, "season": season, "club_id": club["tm_id"], "sources": "bf",
            "checks": "tm_missing", "tm_id": None, "bf_slug": d["slug"],
            "name": " ".join(bf.translit(x).capitalize() for x in (parts[0], parts[-1]))
            if parts else d["slug"],
            "name_bg": short_name(d["full_name"]), "name_bg_approx": 0, "full_name": d["full_name"],
            "slug": None, "shirt": None,
            "position": bg_position(d["position"]), "position_detail": d["position"],
            "position_bg": d["position"],
            "dob": d["dob"], "birth_place": d["birth_place"], "birth_place_bg": d["birth_place"],
            "birth_country": BG_NAT.get(d["birth_country"], d["birth_country"]),
            "born_in_bulgaria": None, "nationalities": "|".join(nats),
            "dual_national": int(len(nats) > 1), "foot": None, "height": None,
            "joined": None, "signed_from": None, "contract_until": None, "market_value": None,
            "photo": None, "youth_raw": "",
            "homegrown": int(club_academy in {y["academy"] for y in yrows}),
            **stat_cols(st, lg, True),
            "comps": json.dumps(d["comps"]),
        })
        for i, y in enumerate(yrows):
            insert(db, "youth_clubs", {"player_id": pid, "season": season, "ord": i, **y})
    db.commit()

    db.execute("""UPDATE players SET born_in_bulgaria =
                  CASE WHEN birth_country IS NULL THEN NULL
                       WHEN birth_country = 'Bulgaria' THEN 1 ELSE 0 END WHERE season = ?""", (season,))
    db.commit()
    if not args.no_nt:
        scrape_national_teams(db, season, page_age)
    fill_academy_names(db, season)

    db.execute("INSERT OR REPLACE INTO meta VALUES ('current_season', ?)", (str(season),))
    db.execute("INSERT OR REPLACE INTO meta VALUES ('updated_at', ?)",
               (datetime.now(timezone.utc).isoformat(timespec="seconds"),))
    for src, ts in data_as_of.items():
        db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (f"data_as_of_{src}",
                   datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")))
    db.commit()

    def count(sql):
        return db.execute(sql, (season,)).fetchone()[0]

    print(f"Done: {count('SELECT COUNT(*) FROM players WHERE season=?')} Bulgarian players -> {DB_PATH}")
    print(f"  with academy data: {count('SELECT COUNT(DISTINCT player_id) FROM youth_clubs WHERE season=?')}")
    for src, n in db.execute("""SELECT source, COUNT(DISTINCT player_id) FROM youth_clubs
                                WHERE season=? GROUP BY source""", (season,)):
        print(f"    from {src}: {n}")
    for code, n in db.execute("""SELECT checks, COUNT(*) FROM players WHERE season=? AND checks<>''
                                 GROUP BY checks ORDER BY 2 DESC""", (season,)):
        print(f"  check {code}: {n}")


if __name__ == "__main__":
    main()


