# efbet League Academies

Bulgarian players in the efbet League (season 2026/27) and the youth academies
they came from, with season stats. BG/EN interface.

```
scraper/   Python: Transfermarkt -> data/youth.sqlite (run on your PC)
api/       PHP: read-only JSON API over the SQLite file
web/       React + Vite frontend (builds to dist/)
tools/     package.py assembles release/ for upload
```

## Data

* **Sources:**
  * Transfermarkt: squad pages (2026/27), player profiles (citizenship,
    birthplace, *Youth clubs*), and club performance pages (efbet League stats).
  * bulgarian-football.com, which is built from official BFU match reports
    (bfunion.bg itself doesn't publish player data): club rosters, nationality,
    date of birth, transfer history with the player's **first registered club**,
    and First League stats.
* **Cross-check:** players are matched by date of birth plus name, falling back
  to name only when the dates differ. Disagreements are stored in
  `players.checks` and listed on the site's Cross-check page:
  `tm_not_bg`, `bf_not_bg`, `bf_missing`, `tm_missing`, `dob_diff`, `club_diff`,
  `stats_diff`. Players that only BFU lists get a negative `id`.
* **Academy evidence** (`youth_clubs.source`): `tm` means Transfermarkt's youth
  clubs, `bf` means the first registered club (with the player's age at the time).
  The BFU archive starts in 2014/15, so for older players this may be their
  first senior club rather than their academy.
* **Who is included:** every squad player with Bulgarian citizenship, dual
  nationals included. `born_in_bulgaria` marks players born in Bulgaria, and
  the site's "Born in Bulgaria only" switch filters on it.
* **Stats:** appearances, minutes, goals, assists, yellow, second yellow and
  red cards, sub on/off. Goalkeeper saves are **not** available: Sofascore's
  API blocks scripted access and Transfermarkt doesn't publish saves.
* **Academies:** youth-club names are normalized in `scraper/academies.py`
  ("PFC Levski Sofia U19" becomes "Levski Sofia"). Add entries to `ALIASES`
  when the same academy shows up twice under different names.
* Transfermarkt's terms don't allow automated collection. The scraper keeps
  the load low (2.5 s between requests, plus an on-disk cache), but keep the
  site non-commercial and credit the source, as the footer does.

* **Competitions:** the league view uses Transfermarkt (which includes assists).
  Cup, Europe and Total come from BFU match reports. Use the switch above any
  player table to change between them.
* **National teams:** the latest call-ups for A, U21, U19 and U17 (Transfermarkt
  squads: current club, caps, goals). Academies come from the same evidence as
  league players. For youth internationals, their current youth team
  ("Levski Sofia U17") also counts.
* **Bulgarian names (BG mode):**
  * Players come from BFU or Transfermarkt's "name in home country". Names
    with no Cyrillic source are transliterated and shown with a dotted
    underline.
  * Clubs and academies come from `ACADEMY_BG` in `scraper/academies.py`,
    then BFU club names. Foreign academies stay in Latin.

## Running it locally

All commands below are for **Windows PowerShell**, run from the project folder
(`C:\Storage\dev\proj\youth-sports`). Run them one line at a time.

### 0. One-time setup

You need Python 3.10+, PHP 8+ and Node.js 18+. Check them:

```powershell
python --version
php --version
node --version
```

PHP must have SQLite enabled. This should print `pdo_sqlite`:

```powershell
php -m | findstr sqlite
```

If it prints nothing, open your `php.ini` (`php --ini` shows where it is) and
remove the `;` in front of `extension=pdo_sqlite`.

Install the scraper and frontend dependencies:

```powershell
python -m pip install -r scraper\requirements.txt
cd web
npm install
cd ..
```

### 1. Get the data (scrape or refresh)

```powershell
python scraper\scrape.py
```

* This writes `data\youth.sqlite`. The first run takes about 30 minutes,
  because it downloads around 750 pages slowly to be polite to the sites.
* Later runs reuse the cache in `scraper\cache\`. They only re-download
  squads, stats and BFU pages older than 12 hours, so a daily refresh takes
  about 15–20 minutes.
* It prints progress per club and national team, then a summary (players,
  academy coverage, cross-check counts).
* Useful options:
  * `--refresh` re-downloads everything now
  * `--no-bf` skips the bulgarian-football.com cross-check
  * `--no-nt` skips the national teams
  * `--season 2027` scrapes 2027/28

If `data\youth.sqlite` already exists, you can skip this step and look at the
site straight away.

### 2a. Preview the site as it will run on jump.bg

Build the frontend, assemble `release\`, and serve it with PHP's built-in
server:

```powershell
cd web
npm run build
cd ..
python tools\package.py
php -S localhost:8000 -t release
```

Open http://localhost:8000 and stop the server with `Ctrl+C`. After a new
scrape, run `python tools\package.py` again (no rebuild needed) and reload
the page. If numbers look old, force-reload with `Ctrl+F5`: the API lets the
browser cache answers for 10 minutes.

### 2b. Development mode (instant reload while editing the frontend)

Use two terminals.

Terminal 1, the PHP API, run from the project folder:

```powershell
php -S localhost:8000
```

Terminal 2, the React dev server:

```powershell
cd web
npm run dev
```

Open http://localhost:5173. Changes in `web\src\` show up immediately, and
calls to `/api` are forwarded to the PHP server in terminal 1. Changes to
`api\index.php` apply on the next request, and a new scrape shows up after a
page reload.

### Troubleshooting

* **"Could not load data" on the page:** the PHP server isn't running, or
  `data\youth.sqlite` doesn't exist yet. Open
  http://localhost:8000/api/index.php?r=meta (or
  http://localhost:5173/api/index.php?r=meta in dev mode), which shows the
  real error.
* **`database not found`:** run step 1 first.
* **Port already in use:** pick another port, e.g. `php -S localhost:8080 -t release`.
  In dev mode, also change the port in `web\vite.config.js`.
* **`package.py` says `dist/ missing`:** run `npm run build` in `web\` first.

## Deploying to jump.bg (shared hosting)

The server needs **only PHP 8 with SQLite**. Node.js and Python run on your PC:
Node compiles the React app into plain HTML/JS/CSS in `release\` (no
`node_modules` is uploaded), and Python produces `data\youth.sqlite`.

1. Build and package, as in step 2a above (`npm run build` in `web\`, then
   `python tools\package.py`).

2. Upload the **contents** of `release/` to `public_html/` (or a subfolder)
   with FTP or cPanel File Manager.
3. In cPanel, use PHP 8.x with the `pdo_sqlite` extension enabled (it is on
   by default on jump.bg).
4. After each scrape, only `data/youth.sqlite` needs re-uploading.

Optional: to keep the database outside the web root, put it at e.g.
`/home/USER/youth-data/youth.sqlite` and create `api/config.php`:

```php
<?php return ['db_path' => '/home/USER/youth-data/youth.sqlite'];
```

`release/data/.htaccess` already blocks direct downloads of the database file.
