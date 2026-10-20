<?php
/**
 * Read-only JSON API over data/youth.sqlite.
 *
 *   ?r=meta                      season, last update, totals
 *   ?r=clubs                     clubs with Bulgarian-player aggregates
 *   ?r=club&id=208               one club + its Bulgarian players
 *   ?r=players                   all Bulgarian players (+ youth clubs)
 *   ?r=player&id=717240          one player (id = Transfermarkt id, negative = BFU-only)
 *   ?r=academies                 academy ranking
 *   ?r=academy&name=Levski+Sofia players who came through an academy
 *   ?r=checks                    players where the two sources disagree
 *   ?r=nt&team=U21               national team squad (A, U21, U19, U17) + academies
 *
 * Optional on every route: &season=2026, &born=1 (born in Bulgaria only).
 */
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: public, max-age=600');

$config = is_file(__DIR__ . '/config.php') ? require __DIR__ . '/config.php' : [];
$dbPath = $config['db_path'] ?? __DIR__ . '/../data/youth.sqlite';

function out($data, int $code = 200): void
{
    http_response_code($code);
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

if (!is_file($dbPath)) {
    out(['error' => 'database not found'], 500);
}

try {
    $db = new PDO('sqlite:' . $dbPath, null, null, [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
    ]);
} catch (PDOException $e) {
    out(['error' => 'database unavailable'], 500);
}

function q(PDO $db, string $sql, array $params = []): array
{
    $st = $db->prepare($sql);
    $st->execute($params);
    return $st->fetchAll();
}

$meta = [];
foreach (q($db, 'SELECT key, value FROM meta') as $row) {
    $meta[$row['key']] = $row['value'];
}
$season = isset($_GET['season']) ? (int)$_GET['season'] : (int)($meta['current_season'] ?? 2026);
$bornOnly = !empty($_GET['born']);
$bornSql = $bornOnly ? ' AND p.born_in_bulgaria = 1' : '';

/** Attach youth clubs to player rows, decode JSON/list fields and cast numbers. */
function withYouth(PDO $db, array $players, int $season, string $idKey = 'id'): array
{
    if (!$players) {
        return [];
    }
    $ids = array_column($players, $idKey);
    $ph = implode(',', array_fill(0, count($ids), '?'));
    $youth = [];
    foreach (q($db, "SELECT y.player_id, y.source, y.name, y.academy, a.name_bg AS academy_bg,
                            y.year_from, y.year_to, y.age_at
                     FROM youth_clubs y LEFT JOIN academies a ON a.academy = y.academy
                     WHERE y.season = ? AND y.player_id IN ($ph) ORDER BY y.player_id, y.ord",
               array_merge([$season], $ids)) as $y) {
        $pid = $y['player_id'];
        unset($y['player_id']);
        $youth[$pid][] = $y;
    }
    $ints = ['id', 'tm_id', 'club_id', 'bf_appearances', 'bf_minutes', 'bf_goals', 'bf_yellow', 'bf_red', 'born_in_bulgaria', 'dual_national', 'homegrown', 'in_squad',
             'appearances', 'goals', 'assists', 'yellow', 'second_yellow', 'red',
             'sub_on', 'sub_off', 'minutes', 'player_id', 'caps', 'in_league', 'name_bg_approx'];
    foreach ($players as &$p) {
        foreach ($ints as $k) {
            if (array_key_exists($k, $p) && $p[$k] !== null) {
                $p[$k] = (int)$p[$k];
            }
        }
        $p['nationalities'] = $p['nationalities'] ? explode('|', $p['nationalities']) : [];
        if (array_key_exists('checks', $p)) {
            $p['checks'] = $p['checks'] ? explode('|', $p['checks']) : [];
        }
        if (array_key_exists('comps', $p)) {
            $p['comps'] = $p['comps'] ? json_decode($p['comps'], true) : null;
        }
        $p['youth_clubs'] = $youth[$p[$idKey]] ?? [];
    }
    return $players;
}

$playerCols = 'p.*, c.name AS club_name, c.name_bg AS club_name_bg';
$route = $_GET['r'] ?? 'meta';

switch ($route) {
    case 'meta':
        $totals = q($db, "SELECT COUNT(*) AS players,
                                 SUM(born_in_bulgaria) AS born_in_bulgaria,
                                 SUM(homegrown) AS homegrown,
                                 SUM(CASE WHEN id IN (SELECT player_id FROM youth_clubs WHERE season = ?)
                                     THEN 1 ELSE 0 END) AS with_youth_data,
                                 SUM(CASE WHEN sources = 'tm+bf' THEN 1 ELSE 0 END) AS confirmed,
                                 SUM(CASE WHEN checks <> '' THEN 1 ELSE 0 END) AS flagged
                          FROM players WHERE season = ?", [$season, $season])[0];
        $seasons = array_map('intval', array_column(
            q($db, 'SELECT DISTINCT season FROM clubs ORDER BY season DESC'), 'season'));
        $teams = q($db, "SELECT t.key, COUNT(n.player_id) AS players FROM nt_teams t
                         LEFT JOIN nt_players n ON n.team = t.key AND n.season = t.season
                         WHERE t.season = ? GROUP BY t.key ORDER BY t.ord", [$season]);
        out(['season' => $season, 'seasons' => $seasons, 'updated_at' => $meta['updated_at'] ?? null,
             'data_as_of' => ['tm' => $meta['data_as_of_tm'] ?? null, 'bf' => $meta['data_as_of_bf'] ?? null],
             'national_teams' => $teams, 'totals' => array_map('intval', $totals)]);

    case 'clubs':
        out(q($db, "SELECT c.tm_id, c.name, c.name_bg, c.slug,
                           COUNT(p.id) AS bulgarians,
                           COALESCE(SUM(p.homegrown), 0) AS homegrown,
                           COALESCE(SUM(p.minutes), 0) AS minutes,
                           COALESCE(SUM(p.goals), 0) AS goals,
                           COALESCE(SUM(p.assists), 0) AS assists
                    FROM clubs c
                    LEFT JOIN players p ON p.club_id = c.tm_id AND p.season = c.season $bornSql
                    WHERE c.season = ?
                    GROUP BY c.tm_id ORDER BY bulgarians DESC, c.name", [$season]));

    case 'club':
        $id = (int)($_GET['id'] ?? 0);
        $club = q($db, 'SELECT tm_id, name, name_bg, slug FROM clubs WHERE tm_id = ? AND season = ?', [$id, $season]);
        if (!$club) {
            out(['error' => 'club not found'], 404);
        }
        $players = q($db, "SELECT $playerCols FROM players p JOIN clubs c
                             ON c.tm_id = p.club_id AND c.season = p.season
                           WHERE p.club_id = ? AND p.season = ? $bornSql
                           ORDER BY p.minutes DESC, p.name", [$id, $season]);
        out(['club' => $club[0], 'players' => withYouth($db, $players, $season)]);

    case 'players':
        $players = q($db, "SELECT $playerCols FROM players p JOIN clubs c
                             ON c.tm_id = p.club_id AND c.season = p.season
                           WHERE p.season = ? $bornSql ORDER BY p.name", [$season]);
        out(withYouth($db, $players, $season));

    case 'player':
        $id = (int)($_GET['id'] ?? 0);
        $players = q($db, "SELECT $playerCols FROM players p JOIN clubs c
                             ON c.tm_id = p.club_id AND c.season = p.season
                           WHERE p.id = ? AND p.season = ?", [$id, $season]);
        if (!$players) {
            out(['error' => 'player not found'], 404);
        }
        out(withYouth($db, $players, $season)[0]);

    case 'academies':
        // A player counts once per academy even if listed there twice.
        out(q($db, "SELECT y.academy, a.name_bg AS academy_bg,
                           COUNT(DISTINCT p.id) AS players,
                           COUNT(DISTINCT p.club_id) AS clubs,
                           SUM(CASE WHEN y.academy = c.academy THEN 1 ELSE 0 END) AS at_own_club,
                           SUM(p.appearances) AS appearances,
                           SUM(p.minutes) AS minutes,
                           SUM(p.goals) AS goals,
                           SUM(p.assists) AS assists
                    FROM (SELECT DISTINCT player_id, season, academy FROM youth_clubs WHERE season = ?) y
                    JOIN players p ON p.id = y.player_id AND p.season = y.season $bornSql
                    JOIN clubs c ON c.tm_id = p.club_id AND c.season = p.season
                    LEFT JOIN academies a ON a.academy = y.academy
                    GROUP BY y.academy
                    ORDER BY players DESC, minutes DESC", [$season]));

    case 'academy':
        $name = (string)($_GET['name'] ?? '');
        $players = q($db, "SELECT $playerCols FROM players p JOIN clubs c
                             ON c.tm_id = p.club_id AND c.season = p.season
                           WHERE p.season = ? $bornSql AND p.id IN
                             (SELECT player_id FROM youth_clubs WHERE season = ? AND academy = ?)
                           ORDER BY p.minutes DESC", [$season, $season, $name]);
        $bg = q($db, 'SELECT name_bg FROM academies WHERE academy = ?', [$name]);
        $nt = q($db, "SELECT n.* FROM nt_players n JOIN nt_teams t ON t.key = n.team AND t.season = n.season
                      WHERE n.season = ? AND n.player_id IN
                        (SELECT player_id FROM youth_clubs WHERE season = ? AND academy = ?)
                      ORDER BY t.ord, n.caps DESC", [$season, $season, $name]);
        out(['academy' => $name, 'academy_bg' => $bg[0]['name_bg'] ?? null,
             'players' => withYouth($db, $players, $season),
             'national' => withYouth($db, $nt, $season, 'player_id')]);

    case 'nt':
        // One national team's latest squad with each player's academies.
        $team = (string)($_GET['team'] ?? 'A');
        $born = $bornOnly ? " AND birth_country = 'Bulgaria'" : '';
        $players = q($db, "SELECT * FROM nt_players WHERE team = ? AND season = ? $born
                           ORDER BY caps DESC, name", [$team, $season]);
        if (!$players && !q($db, 'SELECT 1 FROM nt_teams WHERE key = ? AND season = ?', [$team, $season])) {
            out(['error' => 'team not found'], 404);
        }
        out(['team' => $team, 'players' => withYouth($db, $players, $season, 'player_id')]);

    case 'checks':
        // Players where Transfermarkt and bulgarian-football.com disagree.
        $players = q($db, "SELECT $playerCols FROM players p JOIN clubs c
                             ON c.tm_id = p.club_id AND c.season = p.season
                           WHERE p.season = ? AND p.checks <> '' $bornSql
                           ORDER BY c.name, p.name", [$season]);
        out(withYouth($db, $players, $season));

    default:
        out(['error' => 'unknown route'], 404);
}
