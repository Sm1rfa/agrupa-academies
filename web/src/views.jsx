import { useMemo, useState } from 'react';
import { useApp, link } from './App.jsx';
import { useApi } from './api.js';
import { positionGroup } from './i18n.js';

// ------------------------------------------------------------------ helpers

const fmt = (n) => (n ?? 0).toLocaleString('bg-BG');

function age(dob) {
  if (!dob) return null;
  const d = new Date(dob);
  const now = new Date();
  let a = now.getFullYear() - d.getFullYear();
  if (now < new Date(now.getFullYear(), d.getMonth(), d.getDate())) a--;
  return a;
}

function years(y) {
  if (!y.year_from && !y.year_to) return '';
  return `${y.year_from ?? ''}–${y.year_to ?? ''}`;
}

function Status({ state, children }) {
  const { t } = useApp();
  if (state.loading) return <p className="muted pad">{t('loading')}</p>;
  if (state.error) return <p className="error pad">{t('error')}</p>;
  if (state.data?.error) return <p className="error pad">{t('notFound')}</p>;
  return children(state.data);
}

function YouthChips({ clubs, withYears = false }) {
  const { t, acadName } = useApp();
  if (!clubs?.length) return <span className="muted small">{t('noYouthData')}</span>;
  // One chip per academy; remember which sources mention it.
  const byAcademy = new Map();
  for (const y of clubs) {
    const e = byAcademy.get(y.academy) ?? { ...y, sources: new Set() };
    e.sources.add(y.source);
    byAcademy.set(y.academy, e);
  }
  return (
    <span className="chips">
      {[...byAcademy.values()].map((y) => (
        <a key={y.academy} className={'chip' + (y.sources.size > 1 ? ' both' : '')} href={link('academy', y.academy)}
           title={[...y.sources].map((s) => t('src_' + s)).join(' + ')}>
          {acadName(y)}
          {withYears && years(y) && <em>{years(y)}</em>}
        </a>
      ))}
    </span>
  );
}

function PlayerName({ p }) {
  const { t, nm, country, approx } = useApp();
  return (
    <span className="pname-cell">
      <a className="pname" href={link('player', p.id)}><span {...approx(p)}>{nm(p)}</span></a>
      {p.born_in_bulgaria === 0 && <span className="tag" title={`${t('born')}: ${country(p.birth_country)}`}>{country(p.birth_country)}</span>}
      {p.checks?.length > 0 && <span className="warn" title={p.checks.map((c) => t('check_' + c)).join('\n')}>!</span>}
    </span>
  );
}

/**
 * Sortable table. columns: [{key, label, render?, num?, sort?}]
 */
function SortTable({ rows, columns, initial, rowKey }) {
  const [sort, setSort] = useState(initial);
  const sorted = useMemo(() => {
    const col = columns.find((c) => c.key === sort.key);
    const val = col?.sort ?? ((r) => r[sort.key]);
    return [...rows].sort((a, b) => {
      const x = val(a);
      const y = val(b);
      const cmp = typeof x === 'number' && typeof y === 'number'
        ? x - y
        : String(x ?? '').localeCompare(String(y ?? ''), 'bg');
      return sort.dir === 'asc' ? cmp : -cmp;
    });
  }, [rows, columns, sort]);

  const click = (c) => {
    if (c.sortable === false) return;
    setSort((s) => (s.key === c.key ? { key: c.key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key: c.key, dir: c.num ? 'desc' : 'asc' }));
  };

  return (
    <div className="table-scroll">
      <table className="grid">
        <thead>
          <tr>
            <th className="num rank">#</th>
            {columns.map((c) => (
              <th key={c.key} className={(c.num ? 'num ' : '') + (c.sortable === false ? '' : 'sortable')}
                  onClick={() => click(c)} aria-sort={sort.key === c.key ? (sort.dir === 'asc' ? 'ascending' : 'descending') : undefined}>
                {c.label}
                {sort.key === c.key && <span className="arrow">{sort.dir === 'asc' ? '▲' : '▼'}</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r, i) => (
            <tr key={rowKey(r)}>
              <td className="num rank">{i + 1}</td>
              {columns.map((c) => (
                <td key={c.key} className={c.num ? 'num' : ''}>{c.render ? c.render(r) : r[c.key]}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Stats for the selected competition. "league" uses Transfermarkt (has assists);
 * cup/europe/total come from bulgarian-football.com and are null without BFU data.
 */
function compStats(p, comp) {
  if (comp === 'league') {
    return { appearances: p.appearances, minutes: p.minutes, goals: p.goals, assists: p.assists,
             yellow: p.yellow, red: p.red + p.second_yellow };
  }
  if (!p.comps) return null;
  const c = p.comps[comp] ?? {};
  return { appearances: c.appearances ?? 0, minutes: c.minutes ?? 0, goals: c.goals ?? 0, assists: null,
           yellow: c.yellow ?? 0, red: (c.red ?? 0) + (c.second_yellow ?? 0) };
}

function CompSwitch() {
  const { t, comp, setComp } = useApp();
  return (
    <div className="comp-switch">
      <div className="seg" role="group" aria-label={t('seasonStats')}>
        {['league', 'cup', 'europe', 'total'].map((c) => (
          <button key={c} className={comp === c ? 'on' : ''} onClick={() => setComp(c)}>{t('comp_' + c)}</button>
        ))}
      </div>
      {comp !== 'league' && <span className="muted small">{t('compNote')}</span>}
    </div>
  );
}

function statColumns(app, { club = true, youth = true } = {}) {
  const { t, nm, clubName, comp } = app;
  const st = (p, k) => compStats(p, comp)?.[k];
  const num = (k, label, render) => ({
    key: k, label, num: true, sort: (p) => st(p, k) ?? -1,
    render: (p) => (st(p, k) == null ? <span className="muted">–</span> : render ? render(st(p, k)) : st(p, k)),
  });
  const cols = [
    { key: 'name', label: t('player'), render: (p) => <PlayerName p={p} />, sort: nm },
    { key: 'position', label: t('position'), render: (p) => <span className="small">{t('position_' + positionGroup(p.position))}</span>, sort: (p) => positionGroup(p.position) },
    { key: 'age', label: t('age'), num: true, render: (p) => age(p.dob) ?? '–', sort: (p) => age(p.dob) ?? 0 },
  ];
  if (club) cols.push({ key: 'club_name', label: t('club'), sort: clubName, render: (p) => <a href={link('club', p.club_id)}>{clubName(p)}</a> });
  if (youth) cols.push({ key: 'youth', label: t('youthClubs'), sortable: false, render: (p) => <YouthChips clubs={p.youth_clubs} /> });
  cols.push(
    num('appearances', t('apps')),
    num('minutes', t('minutes'), fmt),
    num('goals', t('goals')),
    num('assists', t('assists')),
    num('yellow', t('yellow'), (v) => (v ? <span className="card y">{v}</span> : '–')),
    num('red', t('red'), (v) => (v ? <span className="card r">{v}</span> : '–')),
  );
  return cols;
}

function Tile({ value, label, accent }) {
  return (
    <div className={'tile' + (accent ? ' accent' : '')}>
      <strong>{fmt(value)}</strong>
      <span>{label}</span>
    </div>
  );
}

// ------------------------------------------------------------------ pages

export function Home() {
  const { t, bornOnly, meta, acadName, pick } = useApp();
  const academies = useApi('academies', { born: bornOnly });
  const clubs = useApi('clubs', { born: bornOnly });
  const tot = meta?.totals;

  return (
    <>
      <section className="hero">
        <h1>{t('siteTitle')}</h1>
        <p>{t('tagline')}</p>
        {tot && (
          <div className="tiles">
            <Tile value={tot.players} label={t('bulgarians')} accent />
            <Tile value={tot.born_in_bulgaria} label={t('bornInBg')} />
            <Tile value={tot.homegrown} label={t('homegrown')} />
            <Tile value={tot.with_youth_data} label={t('withYouthData')} />
            <Tile value={tot.confirmed} label={t('confirmed')} />
            <a className="tile-link" href={link('checks')}><Tile value={tot.flagged} label={t('flagged') + ' →'} /></a>
          </div>
        )}
      </section>

      <div className="two">
        <section className="card-box">
          <div className="box-head">
            <h2>{t('topAcademies')}</h2>
            <a href={link('academies')}>{t('seeAll')} →</a>
          </div>
          <Status state={academies}>
            {(rows) => <Bars rows={rows.slice(0, 12)} label={acadName} value={(r) => r.players} href={(r) => link('academy', r.academy)} />}
          </Status>
        </section>
        <section className="card-box">
          <div className="box-head">
            <h2>{t('clubs')}</h2>
            <a href={link('clubs')}>{t('seeAll')} →</a>
          </div>
          <Status state={clubs}>
            {(rows) => <Bars rows={rows} label={(r) => pick(r.name, r.name_bg)} value={(r) => r.bulgarians} sub={(r) => r.homegrown} subLabel={t('homegrown')} href={(r) => link('club', r.tm_id)} />}
          </Status>
        </section>
      </div>
    </>
  );
}

function Bars({ rows, label, value, sub, subLabel, href }) {
  const max = Math.max(1, ...rows.map(value));
  return (
    <ol className="bars">
      {rows.map((r) => (
        <li key={label(r)}>
          <a href={href(r)}>
            <span className="bar-label">{label(r)}</span>
            <span className="bar-track">
              <span className="bar" style={{ width: `${(value(r) / max) * 100}%` }} />
              {sub && <span className="bar sub" style={{ width: `${(sub(r) / max) * 100}%` }} title={`${subLabel}: ${sub(r)}`} />}
            </span>
            <span className="bar-val">{value(r)}</span>
          </a>
        </li>
      ))}
    </ol>
  );
}

export function Academies() {
  const { t, bornOnly, acadName } = useApp();
  const state = useApi('academies', { born: bornOnly });
  const cols = [
    { key: 'academy', label: t('academy'), sort: acadName, render: (r) => <a href={link('academy', r.academy)}><strong>{acadName(r)}</strong></a> },
    { key: 'players', label: t('players'), num: true },
    { key: 'at_own_club', label: t('atOwnClub'), num: true },
    { key: 'clubs', label: t('clubs'), num: true },
    { key: 'appearances', label: t('apps'), num: true },
    { key: 'minutes', label: t('minutes'), num: true, render: (r) => fmt(r.minutes) },
    { key: 'goals', label: t('goals'), num: true },
    { key: 'assists', label: t('assists'), num: true },
  ];
  return (
    <>
      <h1>{t('academies')}</h1>
      <Status state={state}>
        {(rows) => <SortTable rows={rows} columns={cols} initial={{ key: 'players', dir: 'desc' }} rowKey={(r) => r.academy} />}
      </Status>
    </>
  );
}

export function Academy({ name }) {
  const app = useApp();
  const { t, bornOnly, pick } = app;
  const state = useApi('academy', { name, born: bornOnly });
  return (
    <Status state={state}>
      {(d) => (
        <>
          <p className="crumb"><a href={link('academies')}>{t('academies')}</a> /</p>
          <h1>{pick(d.academy, d.academy_bg)}</h1>
          <div className="tiles">
            <Tile value={d.players.length} label={t('players')} accent />
            <Tile value={new Set(d.players.map((p) => p.club_id)).size} label={t('clubs')} />
            <Tile value={d.players.reduce((s, p) => s + p.minutes, 0)} label={t('minutes')} />
            <Tile value={d.players.reduce((s, p) => s + p.goals, 0)} label={t('goals')} />
          </div>
          <h2>{t('playersFromAcademy')}</h2>
          <CompSwitch />
          <SortTable rows={d.players} columns={statColumns(app)} initial={{ key: 'minutes', dir: 'desc' }} rowKey={(p) => p.id} />
          {d.national.length > 0 && (
            <>
              <h2>{t('fromAcademyNational')}</h2>
              <NationalTable rows={d.national} showTeam />
            </>
          )}
        </>
      )}
    </Status>
  );
}

export function Clubs() {
  const { t, bornOnly, pick } = useApp();
  const state = useApi('clubs', { born: bornOnly });
  return (
    <>
      <h1>{t('clubs')}</h1>
      <Status state={state}>
        {(rows) => (
          <div className="club-grid">
            {rows.map((c) => (
              <a key={c.tm_id} className="club-card" href={link('club', c.tm_id)}>
                <img src={`https://tmssl.akamaized.net/images/wappen/head/${c.tm_id}.png`} alt="" loading="lazy" />
                <strong>{pick(c.name, c.name_bg)}</strong>
                <span className="club-stats">
                  <span><b>{c.bulgarians}</b> {t('bulgarians')}</span>
                  <span><b>{c.homegrown}</b> {t('homegrown')}</span>
                  <span><b>{fmt(c.minutes)}</b> {t('minutes')}</span>
                </span>
              </a>
            ))}
          </div>
        )}
      </Status>
    </>
  );
}

export function Club({ id }) {
  const app = useApp();
  const { t, bornOnly, pick } = app;
  const state = useApi('club', { id, born: bornOnly });
  return (
    <Status state={state}>
      {(d) => (
        <>
          <p className="crumb"><a href={link('clubs')}>{t('clubs')}</a> /</p>
          <h1 className="with-logo">
            <img src={`https://tmssl.akamaized.net/images/wappen/head/${d.club.tm_id}.png`} alt="" />
            {pick(d.club.name, d.club.name_bg)}
          </h1>
          <div className="tiles">
            <Tile value={d.players.length} label={t('bulgarians')} accent />
            <Tile value={d.players.filter((p) => p.homegrown).length} label={t('homegrown')} />
            <Tile value={d.players.reduce((s, p) => s + p.minutes, 0)} label={t('minutes')} />
            <Tile value={d.players.reduce((s, p) => s + p.goals, 0)} label={t('goals')} />
          </div>
          <CompSwitch />
          <SortTable rows={d.players} columns={statColumns(app, { club: false })} initial={{ key: 'minutes', dir: 'desc' }} rowKey={(p) => p.id} />
        </>
      )}
    </Status>
  );
}

export function Players() {
  const app = useApp();
  const { t, bornOnly, clubName } = app;
  const state = useApi('players', { born: bornOnly });
  const [q, setQ] = useState('');
  const [club, setClub] = useState('');
  const [pos, setPos] = useState('');

  return (
    <>
      <h1>{t('players')}</h1>
      <Status state={state}>
        {(rows) => {
          const clubs = [...new Map(rows.map((p) => [p.club_id, clubName(p)])).entries()].sort((a, b) => a[1].localeCompare(b[1], 'bg'));
          const needle = q.trim().toLowerCase();
          const filtered = rows.filter((p) =>
            (!club || String(p.club_id) === club) &&
            (!pos || positionGroup(p.position) === pos) &&
            (!needle || [p.name, p.name_bg, p.full_name, p.club_name, p.club_name_bg,
              ...p.youth_clubs.flatMap((y) => [y.academy, y.academy_bg])]
              .some((s) => s && s.toLowerCase().includes(needle))));
          return (
            <>
              <div className="filters">
                <input type="search" placeholder={t('search')} value={q} onChange={(e) => setQ(e.target.value)} />
                <select value={club} onChange={(e) => setClub(e.target.value)}>
                  <option value="">{t('allClubs')}</option>
                  {clubs.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
                </select>
                <select value={pos} onChange={(e) => setPos(e.target.value)}>
                  <option value="">{t('allPositions')}</option>
                  {['Goalkeeper', 'Defender', 'Midfield', 'Attack'].map((g) => <option key={g} value={g}>{t('position_' + g)}</option>)}
                </select>
                <span className="muted small">{filtered.length} / {rows.length}</span>
              </div>
              <CompSwitch />
              <SortTable rows={filtered} columns={statColumns(app)} initial={{ key: 'minutes', dir: 'desc' }} rowKey={(p) => p.id} />
            </>
          );
        }}
      </Status>
    </>
  );
}

export function Player({ id }) {
  const { t, lang, nm, pick, clubName, acadName, country, approx } = useApp();
  const state = useApi('player', { id });
  const bg = lang === 'bg';
  const date = (d) => (d ? new Date(d).toLocaleDateString(bg ? 'bg-BG' : 'en-GB') : '–');
  return (
    <Status state={state}>
      {(p) => {
        // Subtitle: the full three-part Bulgarian name (BG) or the Cyrillic name (EN).
        const subtitle = bg ? (p.full_name !== nm(p) ? p.full_name : null) : (p.name_bg || null);
        const position = bg ? (p.position_bg || t('position_' + positionGroup(p.position))) : (p.position_detail || p.position);
        const birthPlace = bg ? (p.birth_place_bg || p.birth_place) : p.birth_place;
        const comps = p.comps ? ['league', 'cup', 'supercup', 'europe', 'total'].filter((c) => p.comps[c]) : [];
        return (
          <>
            <p className="crumb"><a href={link('club', p.club_id)}>{clubName(p)}</a> /</p>
            <div className="player-head">
              {p.photo && <img src={p.photo} alt="" />}
              <div>
                <h1><span {...approx(p)}>{nm(p)}</span></h1>
                {subtitle && <p className="muted">{subtitle}</p>}
                <p>{position}{p.shirt && p.shirt !== '-' ? ` · #${p.shirt}` : ''}</p>
              </div>
            </div>

            {p.checks.length > 0 && (
              <div className="notice">
                <strong>{t('crossCheck')}:</strong>
                <ul>{p.checks.map((c) => <li key={c}>{t('check_' + c)}</li>)}</ul>
              </div>
            )}

            <div className="two">
              <section className="card-box">
                <dl className="facts">
                  <dt>{t('born')}</dt>
                  <dd>{date(p.dob)}{p.dob ? ` (${age(p.dob)})` : ''}{birthPlace ? `, ${birthPlace}` : ''}{p.birth_country && p.birth_country !== 'Bulgaria' ? ` (${country(p.birth_country)})` : ''}</dd>
                  <dt>{t('citizenship')}</dt><dd>{p.nationalities.map(country).join(', ')}{p.dual_national ? ` · ${t('dual')}` : ''}</dd>
                  <dt>{t('club')}</dt><dd><a href={link('club', p.club_id)}>{clubName(p)}</a>{p.homegrown ? ` · ${t('homegrown')}` : ''}</dd>
                  {p.joined && <><dt>{t('joined')}</dt><dd>{date(p.joined)}</dd></>}
                  {p.signed_from && <><dt>{t('signedFrom')}</dt><dd>{p.signed_from}</dd></>}
                  {p.contract_until && <><dt>{t('contract')}</dt><dd>{date(p.contract_until)}</dd></>}
                  {p.market_value && p.market_value !== '-' && <><dt>{t('marketValue')}</dt><dd>{p.market_value}</dd></>}
                </dl>
              </section>
              <section className="card-box">
                <h2>{t('youthClubs')}</h2>
                {p.youth_clubs.length ? (
                  <ol className="timeline">
                    {p.youth_clubs.map((y, i) => (
                      <li key={i}>
                        <span className="yrs">{years(y) || '—'}</span>
                        <a href={link('academy', y.academy)}>{acadName(y)}</a>
                        <span className={'src src-' + y.source}>{t('src_' + y.source)}{y.age_at != null ? `, ${t('atAge').replace('{n}', y.age_at)}` : ''}</span>
                      </li>
                    ))}
                  </ol>
                ) : <p className="muted">{t('noYouthData')}</p>}
              </section>
            </div>

            <h2>{t('seasonStats')}</h2>
            <div className="tiles">
              <Tile value={p.appearances} label={t('apps')} accent />
              <Tile value={p.minutes} label={t('minutes')} />
              <Tile value={p.goals} label={t('goals')} />
              <Tile value={p.assists} label={t('assists')} />
              <Tile value={p.yellow} label={t('yellow')} />
              <Tile value={p.red + p.second_yellow} label={t('red')} />
            </div>

            {comps.length > 0 && (
              <>
                <h2>{t('allCompetitions')}</h2>
                <div className="table-scroll compare">
                  <table className="grid">
                    <thead>
                      <tr><th>{t('competition')}</th><th className="num">{t('apps')}</th><th className="num">{t('minutes')}</th>
                        <th className="num">{t('goals')}</th><th className="num">{t('yellow')}</th><th className="num">{t('red')}</th></tr>
                    </thead>
                    <tbody>
                      {comps.map((c) => {
                        const s = p.comps[c];
                        return (
                          <tr key={c} className={c === 'total' ? 'total' : ''}>
                            <td>{t('comp_' + c)}</td><td className="num">{s.appearances}</td><td className="num">{fmt(s.minutes)}</td>
                            <td className="num">{s.goals}</td><td className="num">{s.yellow}</td><td className="num">{s.red + s.second_yellow}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <p className="small muted">{t('bfuSource')}</p>
              </>
            )}

            {p.sources === 'tm+bf' && (
              <>
                <h2>{t('statsCompare')}</h2>
                <div className="table-scroll compare">
                  <table className="grid">
                    <thead>
                      <tr><th>{t('source')}</th><th className="num">{t('apps')}</th><th className="num">{t('minutes')}</th>
                        <th className="num">{t('goals')}</th><th className="num">{t('yellow')}</th><th className="num">{t('red')}</th></tr>
                    </thead>
                    <tbody>
                      <tr><td>Transfermarkt</td><td className="num">{p.appearances}</td><td className="num">{fmt(p.minutes)}</td>
                        <td className="num">{p.goals}</td><td className="num">{p.yellow}</td><td className="num">{p.red + p.second_yellow}</td></tr>
                      <tr><td>bulgarian-football.com</td><td className="num">{p.bf_appearances}</td><td className="num">{fmt(p.bf_minutes)}</td>
                        <td className="num">{p.bf_goals}</td><td className="num">{p.bf_yellow}</td><td className="num">{p.bf_red}</td></tr>
                    </tbody>
                  </table>
                </div>
              </>
            )}

            <p className="small muted links">
              {p.tm_id && <a href={`https://www.transfermarkt.com/${p.slug}/profil/spieler/${p.tm_id}`} target="_blank" rel="noopener noreferrer">Transfermarkt ↗</a>}
              {p.bf_slug && <a href={`https://bulgarian-football.com/players/${p.bf_slug}`} target="_blank" rel="noopener noreferrer">bulgarian-football.com ↗</a>}
            </p>
          </>
        );
      }}
    </Status>
  );
}

export function Checks() {
  const { t, bornOnly, clubName } = useApp();
  const state = useApi('checks', { born: bornOnly });
  const cols = [
    { key: 'name', label: t('player'), render: (p) => <PlayerName p={p} /> },
    { key: 'club_name', label: t('club'), sort: clubName, render: (p) => <a href={link('club', p.club_id)}>{clubName(p)}</a> },
    { key: 'checks', label: t('crossCheck'), sort: (p) => p.checks.join(','),
      render: (p) => <span className="small">{p.checks.map((c) => t('check_' + c)).join('; ')}</span> },
    { key: 'appearances', label: `${t('apps')} TM`, num: true },
    { key: 'bf_appearances', label: `${t('apps')} ${t('bfu')}`, num: true, render: (p) => p.bf_appearances ?? '–', sort: (p) => p.bf_appearances ?? -1 },
    { key: 'goals', label: `${t('goals')} TM`, num: true },
    { key: 'bf_goals', label: `${t('goals')} ${t('bfu')}`, num: true, render: (p) => p.bf_goals ?? '–', sort: (p) => p.bf_goals ?? -1 },
  ];
  return (
    <>
      <h1>{t('crossCheck')}</h1>
      <p className="muted">{t('checksIntro')}</p>
      <Status state={state}>
        {(rows) => rows.length
          ? <SortTable rows={rows} columns={cols} initial={{ key: 'checks', dir: 'asc' }} rowKey={(p) => p.id} />
          : <p>{t('noChecks')}</p>}
      </Status>
    </>
  );
}

// ------------------------------------------------------------------ national teams

/** Player name for a national-team row: links to our page when he plays in the league. */
function NtName({ p }) {
  const { nm, approx } = useApp();
  const label = <span {...approx(p)}>{nm(p)}</span>;
  return p.in_league
    ? <a className="pname" href={link('player', p.player_id)}>{label}</a>
    : <a className="pname" href={`https://www.transfermarkt.com/${p.slug}/profil/spieler/${p.player_id}`} target="_blank" rel="noopener noreferrer">{label}</a>;
}

function NationalTable({ rows, showTeam = false }) {
  const { t, country, pick } = useApp();
  const cols = [
    { key: 'name', label: t('player'), render: (p) => <NtName p={p} /> },
    ...(showTeam ? [{ key: 'team', label: t('national'), render: (p) => t('nt_' + p.team) }] : []),
    { key: 'position', label: t('position'), sort: (p) => positionGroup(p.position),
      render: (p) => <span className="small">{t('position_' + positionGroup(p.position))}</span> },
    { key: 'age', label: t('age'), num: true, render: (p) => age(p.dob) ?? '–', sort: (p) => age(p.dob) ?? 0 },
    { key: 'club', label: t('club'), render: (p) => (
      <span className="nt-club">
        {p.in_league
          ? <a href={link('club', p.club_id)}>{pick(p.club, p.club_bg)}</a>
          : pick(p.club, p.club_bg)}
        {p.league_country && p.league_country !== 'Bulgaria' && <span className="tag">{country(p.league_country)}</span>}
      </span>
    ) },
    { key: 'youth', label: t('youthClubs'), sortable: false, render: (p) => <YouthChips clubs={p.youth_clubs} /> },
    { key: 'caps', label: t('caps'), num: true },
    { key: 'goals', label: t('goals'), num: true },
  ];
  return <SortTable rows={rows} columns={cols} initial={{ key: 'caps', dir: 'desc' }} rowKey={(p) => `${p.team}-${p.player_id}`} />;
}

export function National({ team }) {
  const { t, bornOnly, meta, acadName } = useApp();
  const state = useApi('nt', { team, born: bornOnly });
  const teams = meta?.national_teams ?? [];
  return (
    <>
      <h1>{t('national')}</h1>
      <p className="muted">{t('nationalIntro')}</p>
      <div className="seg tabs" role="tablist">
        {teams.map((tm) => (
          <a key={tm.key} role="tab" aria-selected={tm.key === team} className={tm.key === team ? 'on' : ''}
             href={link('national', tm.key)}>{t('nt_' + tm.key)}</a>
        ))}
      </div>
      <Status state={state}>
        {(d) => {
          const players = d.players;
          const inBg = players.filter((p) => p.league_country === 'Bulgaria').length;
          const abroad = players.filter((p) => p.league_country && p.league_country !== 'Bulgaria').length;
          // Academy ranking for this squad: each player counts once per academy.
          const counts = new Map();
          for (const p of players) {
            for (const y of new Map(p.youth_clubs.map((y) => [y.academy, y])).values()) {
              const e = counts.get(y.academy) ?? { ...y, players: 0 };
              e.players += 1;
              counts.set(y.academy, e);
            }
          }
          const ranking = [...counts.values()].sort((a, b) => b.players - a.players);
          return (
            <>
              <div className="tiles">
                <Tile value={players.length} label={t('players')} accent />
                <Tile value={players.filter((p) => p.in_league).length} label={t('inLeague')} />
                <Tile value={inBg} label={t('inBulgaria')} />
                <Tile value={abroad} label={t('abroad')} />
                <Tile value={players.filter((p) => p.youth_clubs.length).length} label={t('withYouthData')} />
              </div>
              {ranking.length > 0 && (
                <section className="card-box">
                  <h2>{t('academies')}</h2>
                  <Bars rows={ranking.slice(0, 12)} label={acadName} value={(r) => r.players} href={(r) => link('academy', r.academy)} />
                </section>
              )}
              <h2>{t('players')}</h2>
              <NationalTable rows={players} />
            </>
          );
        }}
      </Status>
    </>
  );
}
