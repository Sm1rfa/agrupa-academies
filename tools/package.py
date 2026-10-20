"""Assemble release/ - upload its contents to public_html on the host.

    cd web && npm run build && cd .. && python tools/package.py

release/
  index.html, assets/      built React app
  api/index.php            JSON API
  data/youth.sqlite        database (blocked from direct download by .htaccess)
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REL = ROOT / "release"

if not (ROOT / "dist" / "index.html").exists():
    raise SystemExit("dist/ missing - run `npm run build` in web/ first")
if not (ROOT / "data" / "youth.sqlite").exists():
    raise SystemExit("data/youth.sqlite missing - run scraper/scrape.py first")

# Empty release/ rather than deleting it - on Windows the folder itself may be in
# use (a shell or the preview server sitting in it).
REL.mkdir(exist_ok=True)
for child in REL.iterdir():
    shutil.rmtree(child) if child.is_dir() else child.unlink()
shutil.copytree(ROOT / "dist", REL, dirs_exist_ok=True)
(REL / "api").mkdir()
shutil.copy2(ROOT / "api" / "index.php", REL / "api" / "index.php")
(REL / "data").mkdir()
shutil.copy2(ROOT / "data" / "youth.sqlite", REL / "data" / "youth.sqlite")
(REL / "data" / ".htaccess").write_text(
    "# Never serve the raw database\n"
    "<IfModule mod_authz_core.c>\n  Require all denied\n</IfModule>\n"
    "<IfModule !mod_authz_core.c>\n  Order allow,deny\n  Deny from all\n</IfModule>\n",
    encoding="utf-8")
print(f"Release ready in {REL}")
for p in sorted(REL.rglob("*")):
    if p.is_file():
        print(f"  {p.relative_to(REL)}  ({p.stat().st_size:,} bytes)")
