"""Normalize youth-club names so the same academy is counted once.

Transfermarkt writes academies inconsistently ("PFC Levski Sofia U19",
"Levski Sofia Youth", "Levski"). normalize_academy() strips age-group and
legal-form noise, then applies ALIASES for known variants. Extend ALIASES
when the 'unmatched variants' report from check_academies.py shows dupes.
"""
import re

# lower-cased variant -> canonical academy name
ALIASES = {
    "levski": "Levski Sofia",
    "levski sofia": "Levski Sofia",
    "cska": "CSKA Sofia",
    "cska sofia": "CSKA Sofia",
    "cska-sofia": "CSKA Sofia",
    "zska sofia": "CSKA Sofia",
    "litex lovetch": "Litex Lovech",
    "neftochimic": "Neftochimic Burgas",
    "naftex burgas": "Neftochimic Burgas",
    "chernomorets": "Chernomorets Burgas",
    "chernomorets 1919 burgas": "Chernomorets Burgas",
    "sliven 2000": "Sliven 2000",
    "sliven ofk 2000": "Sliven 2000",
    "spartak plovdiv": "Spartak Plovdiv",
    "chavdar etropole": "Chavdar Etropole",
    "vidima-rakovski": "Vidima-Rakovski Sevlievo",
    "rozova dolina": "Rozova Dolina Kazanlak",
    "genesis football": "Genesis Football Academy",
    "unistar soccer": "UniStar Soccer Academy",
    "cska 1948": "CSKA 1948",
    "cska 1948 sofia": "CSKA 1948",
    "ludogorets": "Ludogorets Razgrad",
    "ludogorets razgrad": "Ludogorets Razgrad",
    "litex": "Litex Lovech",
    "litex lovech": "Litex Lovech",
    "lokomotiv plovdiv": "Lokomotiv Plovdiv",
    "lokomotive plovdiv": "Lokomotiv Plovdiv",
    "lok. plovdiv": "Lokomotiv Plovdiv",
    "lokomotiv sofia": "Lokomotiv Sofia",
    "lok. sofia": "Lokomotiv Sofia",
    "lokomotiv sofia 1929": "Lokomotiv Sofia",
    "botev plovdiv": "Botev Plovdiv",
    "botev vratsa": "Botev Vratsa",
    "cherno more": "Cherno More Varna",
    "cherno more varna": "Cherno More Varna",
    "slavia sofia": "Slavia Sofia",
    "slavia": "Slavia Sofia",
    "beroe": "Beroe Stara Zagora",
    "beroe stara zagora": "Beroe Stara Zagora",
    "septemvri sofia": "Septemvri Sofia",
    "septemvri": "Septemvri Sofia",
    "spartak varna": "Spartak Varna",
    "arda kardzhali": "Arda Kardzhali",
    "arda": "Arda Kardzhali",
    "dunav ruse": "Dunav Ruse",
    "dunav": "Dunav Ruse",
    "chernomorets burgas": "Chernomorets Burgas",
    "neftochimic burgas": "Neftochimic Burgas",
    "pirin blagoevgrad": "Pirin Blagoevgrad",
    "montana": "Montana",
    "etar veliko tarnovo": "Etar Veliko Tarnovo",
    "etar": "Etar Veliko Tarnovo",
    "botev galabovo": "Botev Galabovo",
    "lokomotiv gorna oryahovitsa": "Lokomotiv Gorna Oryahovitsa",
    "minyor pernik": "Minyor Pernik",
    "vitosha bistritsa": "Vitosha Bistritsa",
    "marek dupnitsa": "Marek Dupnitsa",
    "spartak pleven": "Spartak Pleven",
    "hebar pazardzhik": "Hebar Pazardzhik",
    "krumovgrad": "Krumovgrad",
    "strumska slava": "Strumska Slava",
    "nesebar": "Nesebar",
    "volov shumen": "Volov Shumen",
    "pirin gotse delchev": "Pirin Gotse Delchev",
}

# Canonical academy -> Bulgarian display name. Bulgarian clubs not listed here get
# their name from bulgarian-football.com (first registered club); foreign academies
# stay in Latin.
ACADEMY_BG = {
    "Levski Sofia": "Левски (София)",
    "CSKA Sofia": "ЦСКА (София)",
    "CSKA 1948": "ЦСКА 1948 (София)",
    "Ludogorets Razgrad": "Лудогорец (Разград)",
    "Litex Lovech": "Литекс (Ловеч)",
    "Lokomotiv Plovdiv": "Локомотив (Пловдив)",
    "Lokomotiv Sofia": "Локомотив (София)",
    "Botev Plovdiv": "Ботев (Пловдив)",
    "Botev Vratsa": "Ботев (Враца)",
    "Cherno More Varna": "Черно море (Варна)",
    "Slavia Sofia": "Славия (София)",
    "Beroe Stara Zagora": "Берое (Стара Загора)",
    "Septemvri Sofia": "Септември (София)",
    "Spartak Varna": "Спартак (Варна)",
    "Arda Kardzhali": "Арда (Кърджали)",
    "Dunav Ruse": "Дунав (Русе)",
    "Chernomorets Burgas": "Черноморец (Бургас)",
    "Neftochimic Burgas": "Нефтохимик (Бургас)",
    "Pirin Blagoevgrad": "Пирин (Благоевград)",
    "Pirin Gotse Delchev": "Пирин (Гоце Делчев)",
    "Montana": "Монтана",
    "Etar Veliko Tarnovo": "Етър (Велико Търново)",
    "Botev Galabovo": "Ботев (Гълъбово)",
    "Lokomotiv Gorna Oryahovitsa": "Локомотив (Горна Оряховица)",
    "Lokomotiv Mezdra": "Локомотив (Мездра)",
    "Minyor Pernik": "Миньор (Перник)",
    "Vitosha Bistritsa": "Витоша (Бистрица)",
    "Marek Dupnitsa": "Марек (Дупница)",
    "Spartak Pleven": "Спартак (Плевен)",
    "Spartak Plovdiv": "Спартак (Пловдив)",
    "Hebar Pazardzhik": "Хебър (Пазарджик)",
    "Krumovgrad": "Крумовград",
    "Strumska Slava": "Струмска слава (Радомир)",
    "Nesebar": "Несебър",
    "Belasitsa Petrich": "Беласица (Петрич)",
    "Bankya": "Банкя",
    "Chavdar Etropole": "Чавдар (Етрополе)",
    "DIT Sofia": "ДИТ (София)",
    "Levski Elin Pelin": "Левски (Елин Пелин)",
    "Rodopi Momchilgrad": "Родопи (Момчилград)",
    "Rozova Dolina Kazanlak": "Розова долина (Казанлък)",
    "Sliven 2000": "Сливен 2000",
    "Svoboda Milkovitsa": "Свобода (Милковица)",
    "Trayana Stara Zagora": "Траяна (Стара Загора)",
    "Tsarsko Selo Sofia": "Царско село (София)",
    "Vidima-Rakovski Sevlievo": "Видима-Раковски (Севлиево)",
    "Vihar Aytos": "Вихър (Айтос)",
    "Volov Shumen": "Волов (Шумен)",
    "Dobrudzha Dobrich": "Добруджа (Добрич)",
    "Yantra Gabrovo": "Янтра (Габрово)",
    "Botev 57": "Ботев 57 (София)",
    "Miziya Knezha": "Мизия (Кнежа)",
    "Olympic Varna": "Олимпик (Варна)",
    "Sevlievo": "Севлиево",
    "Sozopol": "Созопол",
}

# Noise tokens removed before alias lookup (age groups, reserves, legal forms).
_NOISE = re.compile(
    r"\b(u\s?-?\d{1,2}|under\s?\d{2}|youth|yth\.?|academy|akademia|akademiya|juniors?|"
    r"reserves?|iii|ii|b|pfc|pfk|pofk|fc|fk|ofc|ofk|sfc|sk|ac|cf|sc|1912|1914)\b\.?",
    re.IGNORECASE,
)


def normalize_academy(name):
    if not name:
        return None
    base = name.strip()
    key = base.lower()
    if key in ALIASES:
        return ALIASES[key]
    cleaned = " ".join(_NOISE.sub(" ", base).split()).strip(" .-")
    ck = cleaned.lower()
    if ck in ALIASES:
        return ALIASES[ck]
    return cleaned or base
