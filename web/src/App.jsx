import { createContext, useContext, useEffect, useState } from 'react';
import { STRINGS, COUNTRIES_BG } from './i18n.js';
import { useApi } from './api.js';
import { Home, Academies, Academy, Clubs, Club, Players, Player, Checks, National } from './views.jsx';

const Ctx = createContext(null);
export const useApp = () => useContext(Ctx);

function readPref(key, fallback) {
  try {
    const v = localStorage.getItem(key);
    return v === null ? fallback : JSON.parse(v);
  } catch {
    return fallback;
  }
}

function writePref(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable - preference just won't persist */
  }
}

/** '#/club/208' -> ['club', '208'] */
function useHashRoute() {
  const parse = () => window.location.hash.replace(/^#\/?/, '').split('/').map(decodeURIComponent);
  const [route, setRoute] = useState(parse);
  useEffect(() => {
    const on = () => {
      setRoute(parse());
      window.scrollTo(0, 0);
    };
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);
  return route;
}

export const link = (...parts) => '#/' + parts.map(encodeURIComponent).join('/');

export default function App() {
  const [lang, setLang] = useState(() => readPref('lang', 'bg'));
  const [bornOnly, setBornOnly] = useState(() => readPref('bornOnly', false));
  const [comp, setComp] = useState(() => readPref('comp', 'league'));
  const [page, arg] = useHashRoute();
  const meta = useApi('meta');

  useEffect(() => {
    writePref('lang', lang);
    document.documentElement.lang = lang;
    document.title = STRINGS[lang].siteTitle;
  }, [lang]);
  useEffect(() => writePref('bornOnly', bornOnly), [bornOnly]);
  useEffect(() => writePref('comp', comp), [comp]);

  const t = (k) => STRINGS[lang][k] ?? k;
  const bg = lang === 'bg';
  // Display names: Cyrillic in BG mode when the data has it, Latin otherwise.
  const ctx = {
    lang, t, bornOnly, comp, setComp, meta: meta.data,
    pick: (en, bgName) => (bg && bgName) || en,
    nm: (p) => (bg && p.name_bg) || p.name,
    // Transliterated (not sourced) Cyrillic names get a dotted underline + tooltip.
    approx: (p) => (bg && p.name_bg_approx ? { className: 'approx', title: STRINGS.bg.approxName } : {}),
    clubName: (p) => (bg && p.club_name_bg) || p.club_name,
    acadName: (y) => (bg && y.academy_bg) || y.academy,
    country: (c) => (bg && COUNTRIES_BG[c]) || c,
  };

  let view;
  switch (page) {
    case 'academies': view = <Academies />; break;
    case 'academy': view = <Academy name={arg} />; break;
    case 'clubs': view = <Clubs />; break;
    case 'club': view = <Club id={arg} />; break;
    case 'players': view = <Players />; break;
    case 'player': view = <Player id={arg} />; break;
    case 'checks': view = <Checks />; break;
    case 'national': view = <National team={arg || 'A'} />; break;
    default: view = <Home />;
  }

  const nav = [['', 'navHome'], ['academies', 'navAcademies'], ['clubs', 'navClubs'], ['players', 'navPlayers'], ['national', 'navNational'], ['checks', 'navChecks']];
  const active = (key) => (page || '') === key || (key && page === key.replace(/s$/, ''));
  const season = meta.data?.season;

  return (
    <Ctx.Provider value={ctx}>
      <header className="top">
        <div className="wrap top-inner">
          <a className="brand" href="#/">
            <span className="flag" aria-hidden="true"><i /><i /><i /></span>
            <span>
              <strong>{t('siteTitle')}</strong>
              {season && <small>{t('season')} {season}/{String((season + 1) % 100).padStart(2, '0')}</small>}
            </span>
          </a>
          <nav className="nav">
            {nav.map(([key, label]) => (
              <a key={key} href={link(key).replace(/\/$/, '/')} className={active(key) ? 'on' : ''}>{t(label)}</a>
            ))}
          </nav>
          <div className="tools">
            <label className="toggle">
              <input type="checkbox" checked={bornOnly} onChange={(e) => setBornOnly(e.target.checked)} />
              <span>{t('bornOnly')}</span>
            </label>
            <div className="lang" role="group" aria-label="Language">
              {['bg', 'en'].map((l) => (
                <button key={l} className={lang === l ? 'on' : ''} onClick={() => setLang(l)}>{l.toUpperCase()}</button>
              ))}
            </div>
          </div>
        </div>
      </header>
      <main className="wrap">{view}</main>
      <footer className="wrap foot">
        <p>{t('sourceNote')} {t('gkNote')}</p>
        {meta.data?.data_as_of && (
          <p>
            {t('dataAsOf')}: {[['tm', 'Transfermarkt'], ['bf', 'bulgarian-football.com']]
              .filter(([k]) => meta.data.data_as_of[k])
              .map(([k, label]) => `${label} ${new Date(meta.data.data_as_of[k]).toLocaleString(bg ? 'bg-BG' : 'en-GB', { dateStyle: 'medium', timeStyle: 'short' })}`)
              .join(' · ')}
          </p>
        )}
      </footer>
    </Ctx.Provider>
  );
}
