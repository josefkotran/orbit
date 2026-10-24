<?php
/**
 * Návštěvy orbit.easya.cz (only for the owner, behind a password): who came, from where, what they looked at, and who
 * downloaded or installed Orbit. Robots and pages nobody looked at are left out. Data: lib/stats.php, login:
 * lib/admin.php. Written for PHP 7.4+.
 */
declare(strict_types=1);

require_once dirname(__DIR__) . '/lib/admin.php';

header('Cache-Control: no-store, private');
header('X-Robots-Tag: noindex, nofollow');
header('Referrer-Policy: same-origin');
header('X-Frame-Options: DENY');
// the same as admin/.htaccess (that one wins on the hosting; php -S in the tests has only this)
header("Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'");

const PERIODS = [1 => 'Dnes', 7 => '7 dní', 30 => '30 dní', 90 => '90 dní'];
const CONVERTED = ['install', 'run', 'download', 'copy'];

function h($s): string
{
    return htmlspecialchars((string)$s, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

/** 1 návštěva, 2 návštěvy, 5 návštěv */
function plural(int $n, string $one, string $few, string $many): string
{
    return $n === 1 ? $one : ($n >= 2 && $n <= 4 ? $few : $many);
}

function dur(int $s): string
{
    if ($s < 60) {
        return $s . ' s';
    }
    if ($s < 3600) {
        $m = intdiv($s, 60);
        $r = $s % 60;
        return $m . ' min' . ($r && $m < 10 ? ' ' . $r . ' s' : '');
    }
    $hh = intdiv($s, 3600);
    $m = intdiv($s % 3600, 60);
    return $hh . ' h' . ($m ? ' ' . $m . ' min' : '');
}

function dayLabel(int $t, int $now): string
{
    $d = date('Y-m-d', $t);
    if ($d === date('Y-m-d', $now)) {
        return 'Dnes';
    }
    if ($d === date('Y-m-d', strtotime('-1 day', $now))) {
        return 'Včera';
    }
    $names = ['neděle', 'pondělí', 'úterý', 'středa', 'čtvrtek', 'pátek', 'sobota'];
    return $names[(int)date('w', $t)] . ' ' . date('j. n.', $t);
}

function country(?string $c): string
{
    static $names = [
        'CZ' => 'Česko', 'SK' => 'Slovensko', 'DE' => 'Německo', 'AT' => 'Rakousko', 'PL' => 'Polsko', 'HU' => 'Maďarsko',
        'US' => 'USA', 'GB' => 'Velká Británie', 'IE' => 'Irsko', 'FR' => 'Francie', 'NL' => 'Nizozemsko', 'BE' => 'Belgie',
        'CH' => 'Švýcarsko', 'IT' => 'Itálie', 'ES' => 'Španělsko', 'PT' => 'Portugalsko', 'SE' => 'Švédsko', 'NO' => 'Norsko',
        'DK' => 'Dánsko', 'FI' => 'Finsko', 'UA' => 'Ukrajina', 'RU' => 'Rusko', 'CA' => 'Kanada', 'IN' => 'Indie',
        'CN' => 'Čína', 'JP' => 'Japonsko', 'BR' => 'Brazílie', 'AU' => 'Austrálie', 'SG' => 'Singapur', 'RO' => 'Rumunsko',
        'HR' => 'Chorvatsko', 'SI' => 'Slovinsko', 'BG' => 'Bulharsko', 'GR' => 'Řecko', 'TR' => 'Turecko', 'IL' => 'Izrael',
        'LT' => 'Litva', 'LV' => 'Lotyšsko', 'EE' => 'Estonsko', 'VN' => 'Vietnam', 'KR' => 'Jižní Korea', 'HK' => 'Hongkong',
        'TW' => 'Tchaj-wan', 'MX' => 'Mexiko', 'LU' => 'Lucembursko', 'T1' => 'Tor (anonymně)',
    ];
    return $c === null ? 'neznámá země' : ($names[$c] ?? $c);
}

function language(?string $l): ?string
{
    static $names = ['cs' => 'čeština', 'sk' => 'slovenština', 'en' => 'angličtina', 'de' => 'němčina', 'pl' => 'polština',
        'ru' => 'ruština', 'uk' => 'ukrajinština', 'fr' => 'francouzština', 'es' => 'španělština', 'it' => 'italština',
        'hu' => 'maďarština', 'nl' => 'nizozemština'];
    return $l === null ? null : ($names[$l] ?? $l);
}

/** "počítač s Windows", "iPhone", "telefon s Androidem" */
function machine(array $v): string
{
    $os = $v['os'];
    $d = $v['device'];
    if ($os === null) {
        return 'neznámé zařízení';
    }
    if ($os === 'iOS') {
        return $d === 'tablet' ? 'iPad' : 'iPhone';
    }
    $with = ['Windows' => 's Windows', 'macOS' => '', 'Android' => 's Androidem', 'Linux' => 's Linuxem', 'ChromeOS' => ''];
    if ($os === 'macOS') {
        return 'Mac';
    }
    if ($os === 'ChromeOS') {
        return 'Chromebook';
    }
    $what = $d === 'mobile' ? 'telefon' : ($d === 'tablet' ? 'tablet' : 'počítač');
    return trim($what . ' ' . ($with[$os] ?? ''));
}

function fetcherLabel(string $kind): string
{
    $names = ['powershell' => 'PowerShell', 'claude' => 'Claude', 'curl' => 'curl', 'browser' => 'prohlížeč'];
    return $names[$kind] ?? 'jiný program';
}

/** The visit as steps in time order: parts of the page with how long they were on screen, and what was done there. */
function steps(array $v): array
{
    $out = [];
    $soundShown = false;
    foreach ($v['items'] as $item) {
        [, $kind, $x] = $item;
        if ($kind === 'sec') {
            $ms = (int)($v['sections'][$x][0] ?? 0);
            if ($ms < 1500 && $x !== 'instalace') {
                continue;   // scrolled past
            }
            $out[] = ['sec', Stats::SECTIONS[$x], $ms >= 1000 ? dur(intdiv($ms, 1000)) : 'jen průjezdem'];
            continue;
        }
        if ($kind === 'srv') {
            $who = (string)$x['m'];
            if ($x['e'] === 'script') {
                $label = $who === 'powershell' ? 'Instalace spuštěná v PowerShellu'
                    : ($who === 'claude' ? 'Claude si přečetl instalační skript'
                    : ($who === 'browser' ? 'Instalační skript v prohlížeči' : 'Instalační skript stažený'));
                $out[] = [$who === 'powershell' ? 'good' : 'act', $label, in_array($who, ['powershell', 'claude', 'browser'], true) ? '' : fetcherLabel($who)];
            } else {
                $last = end($out);
                if ($who === 'powershell' && $last && $last[1] === 'Instalace spuštěná v PowerShellu') {
                    $out[key($out)][2] = 'stahuje instalátor';
                } else {
                    $out[] = [$who === 'powershell' ? 'good' : 'act', $who === 'powershell' ? 'Instalátor se stahuje příkazem' : 'Popis vydání', fetcherLabel($who)];
                }
            }
            continue;
        }
        $m = (string)($x['m'] ?? '');
        switch ($x['e']) {
            case 'download':
                $out[] = ['good', 'Stažení instalátoru', isset(Stats::PLACES[$m]) ? 'tlačítko ' . Stats::PLACES[$m] : ''];
                break;
            case 'copy':
                [$what, $where] = array_pad(explode(':', $m, 2), 2, '');  // "prikaz:uvod"; before 24 Oct just "prikaz"
                $out[] = ['good', $what === 'prikaz' ? 'Zkopírovaný příkaz pro PowerShell'
                    : ($what === 'rucne' ? 'Ručně zkopírovaná instalace' : 'Zkopírované zadání pro Claude Code'), Stats::PLACES[$where] ?? ''];
                break;
            case 'script_view':
                $out[] = ['act', 'Otevřený instalační skript', ''];
                break;
            case 'github':
                $out[] = ['act', $m === 'issues' ? 'GitHub Issues' : 'GitHub', $m === 'issues' ? '' : (Stats::PLACES[$m] ?? '')];
                break;
            case 'link':
                $out[] = ['act', 'Odkaz', $m];
                break;
            case 'video_sound':
                if (!$soundShown) {
                    $soundShown = true;
                    $vs = $v['video'];
                    $out[] = ['act', 'Video se zvukem', ($vs['sound'] ? dur($vs['sound']) : '') . ($vs['max'] ? ', do ' . $vs['max'] . ' %' : '')];
                }
                break;
            case 'demo':
                $out[] = ['act', 'Ukázka diktování', $v['demo'] > 1 ? $v['demo'] . '×' : ''];
                break;
            case 'feature':
            case 'faq':
                $name = $x['e'] === 'feature' ? (Stats::FEATURES[$m] ?? '') : $m;
                if ($name === '') {
                    break;
                }
                $group = $x['e'] === 'feature' ? 'Funkce' : 'Otázky';
                $last = end($out);
                if ($last && $last[1] === $group) {
                    $out[key($out)][2] .= ', ' . $name;
                } else {
                    $out[] = ['act', $group, $name];
                }
                break;
            case 'theme':
                $colors = ['blue' => 'modrá', 'violet' => 'fialová', 'teal' => 'tyrkysová'];
                $out[] = ['sec', 'Barva stránky', $colors[$m] ?? $m];
                break;
        }
    }
    return array_slice($out, 0, 18);
}

const RESULTS = [
    'install' => ['Instalace příkazem', 'terminal'],
    'run' => ['Spuštěná instalace', 'terminal'],
    'download' => ['Stažení instalátoru', 'download'],
    'copy' => ['Zkopírovaná instalace', 'copy'],
    'reached' => ['Až k instalaci', 'eye'],
    'browse' => ['Prohlížení', 'eye'],
    'brief' => ['Krátce', 'eye'],
];

function tally(array $visits): array
{
    $t = ['people' => 0, 'download' => 0, 'copy' => 0, 'install' => 0, 'live' => 0, 'explored' => 0, 'reached' => 0, 'converted' => 0, 'windows' => 0];
    foreach ($visits as $v) {
        if ($v['run']) {
            $t['install']++;
        }
        if ($v['only_cmd']) {
            continue;
        }
        $t['people']++;
        $t['download'] += in_array('download', $v['did'], true) ? 1 : 0;
        $t['copy'] += in_array('copy', $v['did'], true) ? 1 : 0;
        $t['live'] += $v['live'] ? 1 : 0;
        $t['explored'] += $v['result'] !== 'brief' ? 1 : 0;
        $t['reached'] += in_array($v['result'], array_merge(CONVERTED, ['reached']), true) ? 1 : 0;
        $t['converted'] += in_array($v['result'], CONVERTED, true) || $v['run'] ? 1 : 0;
        $t['windows'] += $v['os'] === 'Windows' ? 1 : 0;
    }
    return $t;
}

function counts(array $visits, callable $key): array
{
    $c = [];
    foreach ($visits as $v) {
        if ($v['only_cmd']) {
            continue;
        }
        foreach ((array)$key($v) as $k) {
            if ($k !== null && $k !== '') {
                $c[$k] = ($c[$k] ?? 0) + 1;
            }
        }
    }
    arsort($c);
    return $c;
}

function median(array $xs): int
{
    if (!$xs) {
        return 0;
    }
    sort($xs);
    $n = count($xs);
    return (int)($n % 2 ? $xs[intdiv($n, 2)] : ($xs[$n / 2 - 1] + $xs[$n / 2]) / 2);
}

function bars(array $c, int $limit = 8, ?callable $label = null, array $notes = []): string
{
    if (!$c) {
        return '<p class="note">Zatím nic.</p>';
    }
    $max = max($c);
    $html = '<ul class="bars">';
    $i = 0;
    $rest = 0;
    foreach ($c as $k => $n) {
        if ($i++ >= $limit) {
            $rest += $n;
            continue;
        }
        $html .= '<li><span class="l">' . h($label ? $label((string)$k) : $k) . (isset($notes[$k]) ? '<small>' . h($notes[$k]) . '</small>' : '')
            . '</span><span class="v">' . $n . '</span><span class="b"><i style="width:' . max(2, round($n / $max * 100)) . '%"></i></span></li>';
    }
    if ($rest) {
        $html .= '<li><span class="l">ostatní</span><span class="v">' . $rest . '</span></li>';
    }
    return $html . '</ul>';
}

function delta(int $now, int $before, string $what): string
{
    $d = $now - $before;
    if ($d === 0) {
        return 'stejně jako ' . $what;
    }
    return '<span class="' . ($d > 0 ? 'up' : 'down') . '">' . ($d > 0 ? '▲ +' : '▼ −') . abs($d) . '</span> proti ' . $what;
}

function redirect(string $to): void
{
    header('Location: ' . $to, true, 303);
    exit;
}

function icon(string $name): string
{
    return '<svg aria-hidden="true"><use href="#i-' . h($name) . '"/></svg>';
}

const ICONS = <<<SVG
<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>
<symbol id="i-orbit" viewBox="0 0 32 32"><g transform="rotate(-24 16 16)"><path d="M3 16a13 4.6 0 0 1 26 0" fill="none" stroke="currentColor" stroke-width="1.4" opacity=".5"/><circle cx="16" cy="16" r="6.6" fill="currentColor"/><path d="M3 16a13 4.6 0 0 0 26 0" fill="none" stroke="#04060C" stroke-width="2.8"/><path d="M3 16a13 4.6 0 0 0 26 0" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/><circle r="1.9" cx="25.9" cy="19" fill="#EEF2FA" stroke="#04060C" stroke-width="1"/></g></symbol>
<symbol id="i-download" viewBox="0 0 24 24"><path d="M12 4v11m0 0l-4.5-4.5M12 15l4.5-4.5M5 19.5h14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></symbol>
<symbol id="i-copy" viewBox="0 0 24 24"><rect x="8.5" y="8.5" width="11" height="11" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M15.5 8.5V6.5a2 2 0 0 0-2-2h-7a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h2" fill="none" stroke="currentColor" stroke-width="1.8"/></symbol>
<symbol id="i-terminal" viewBox="0 0 24 24"><rect x="3" y="4.5" width="18" height="15" rx="3" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M7 9.5l3 2.5-3 2.5M12.5 15h4.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></symbol>
<symbol id="i-eye" viewBox="0 0 24 24"><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="1.8"/></symbol>
<symbol id="i-pin" viewBox="0 0 24 24"><path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0C18.5 15.4 12 21 12 21z" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="10" r="2.3" fill="currentColor"/></symbol>
<symbol id="i-device" viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="11.5" rx="2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M8.5 19.5h7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></symbol>
<symbol id="i-from" viewBox="0 0 24 24"><path d="M14 5h5v14h-5M4 12h11m0 0l-4-4m4 4l-4 4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></symbol>
<symbol id="i-lang" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M3.5 12h17M12 3.5c2.6 2.4 3.6 5.2 3.6 8.5s-1 6.1-3.6 8.5c-2.6-2.4-3.6-5.2-3.6-8.5s1-6.1 3.6-8.5z" fill="none" stroke="currentColor" stroke-width="1.5"/></symbol>
</defs></svg>
SVG;

function page(string $title, string $body, bool $withScript = false): void
{
    $v = static function (string $file): string {
        return substr(md5((string)@filemtime(__DIR__ . '/' . $file)), 0, 8);
    };
    echo '<!doctype html><html lang="cs"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        . '<meta name="robots" content="noindex,nofollow"><title>' . h($title) . '</title>'
        . '<link rel="icon" href="../assets/favicon.svg" type="image/svg+xml">'
        . '<link rel="stylesheet" href="admin.css?v=' . $v('admin.css') . '"></head><body>' . ICONS . $body
        . ($withScript ? '<script src="admin.js?v=' . $v('admin.js') . '"></script>' : '') . '</body></html>';
    exit;
}

function loginPage(string $error = ''): void
{
    $account = Admin::account() !== null;
    $body = '<main class="login"><form method="post" action="./">'
        . '<div class="brand">' . icon('orbit') . 'Orbit</div>';
    if (!$account) {
        $body .= '<div class="err">Heslo ještě není nastavené. Nastaví ho na počítači příkaz '
            . '<code>python web\\publish.py --admin-password</code>.</div>';
    } else {
        $body .= '<input type="hidden" name="action" value="login">'
            . '<label for="pw">Heslo</label><input id="pw" name="password" type="password" autocomplete="current-password" required autofocus>'
            . ($error !== '' ? '<div class="err">' . h($error) . '</div>' : '')
            . '<button class="btn" type="submit">Přihlásit</button>';
    }
    $body .= '<a class="back" href="../">Zpět na web</a></form></main>';
    page('Přihlášení · Orbit', $body);
}

// ---------------------------------------------------------------- requests

$days = (int)($_GET['d'] ?? 7);
if (!isset(PERIODS[$days])) {
    $days = 7;
}
$self = './?d=' . $days;

if (($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'POST') {
    if (!Admin::sameOrigin()) {
        http_response_code(403);
        exit('Požadavek nepřišel z této stránky.');
    }
    $action = (string)($_POST['action'] ?? '');
    if ($action === 'login') {
        $wait = Admin::lockedFor();
        if ($wait !== null) {
            loginPage('Moc špatných hesel za sebou. Další pokus půjde za ' . dur($wait) . '.');
        }
        if (Admin::verify((string)($_POST['password'] ?? ''))) {
            Admin::logIn();
            redirect('./');
        }
        Admin::failed();
        loginPage('Heslo nesouhlasí.');
    }
    if (!Admin::loggedIn() || !Admin::csrfOk($_POST['csrf'] ?? null)) {
        http_response_code(403);
        loginPage('Přihlášení vypršelo, přihlas se znovu.');
    }
    if ($action === 'logout') {
        Admin::logOut();
        redirect('./');
    }
    if ($action === 'forget') {
        $ids = explode(',', (string)($_POST['ids'] ?? ''));
        $t0 = (int)($_POST['t0'] ?? 0);
        $t1 = (int)($_POST['t1'] ?? 0);
        $n = $t0 > 0 && $t1 >= $t0 && $t1 - $t0 < 3 * 86400 ? Stats::forget($ids, $t0 - 3600, $t1 + 3600) : 0;
        redirect($self . '&msg=' . ($n > 0 ? 'forgot' : 'nothing'));
    }
    if ($action === 'password') {
        $old = (string)($_POST['old'] ?? '');
        $new = (string)($_POST['new'] ?? '');
        if (!Admin::verify($old)) {
            redirect('./?heslo=1&msg=old');
        }
        if (strlen($new) < Admin::MIN_PASSWORD || $new !== (string)($_POST['again'] ?? '')) {
            redirect('./?heslo=1&msg=new');
        }
        if (!Admin::setPassword($new)) {
            redirect('./?heslo=1&msg=fail');
        }
        Admin::logIn();
        redirect('./?msg=password');
    }
    redirect($self);
}

if (!Admin::loggedIn()) {
    loginPage();
}
Admin::logIn();  // every visit extends the login and keeps this browser out of the statistics

$csrf = Admin::csrf();
$msg = (string)($_GET['msg'] ?? '');
$top = '<header class="top"><div class="wrap"><a class="brand" href="./">' . icon('orbit') . 'Orbit</a>'
    . '<nav class="period" aria-label="Období">';
foreach (PERIODS as $d => $label) {
    $top .= '<a href="./?d=' . $d . '"' . ($d === $days && !isset($_GET['heslo']) ? ' aria-current="page"' : '') . '>' . $label . '</a>';
}
$top .= '</nav><a class="site" href="../" target="_blank" rel="noopener">Web ↗</a>'
    . '<form method="post" action="./"><input type="hidden" name="csrf" value="' . h($csrf) . '"><input type="hidden" name="action" value="logout">'
    . '<button class="link" type="submit">Odhlásit</button></form></div></header>';

if (isset($_GET['heslo'])) {
    $errors = ['old' => 'Současné heslo nesouhlasí.', 'new' => 'Nové heslo musí mít aspoň ' . Admin::MIN_PASSWORD . ' znaků a obě musí být stejná.',
        'fail' => 'Heslo se nepodařilo uložit.'];
    $body = $top . '<main class="login" style="min-height:auto;padding-top:48px"><form method="post" action="./">'
        . '<input type="hidden" name="csrf" value="' . h($csrf) . '"><input type="hidden" name="action" value="password">'
        . '<p style="font-size:16px;color:var(--text)">Změna hesla</p>'
        . '<label for="o">Současné heslo</label><input id="o" name="old" type="password" autocomplete="current-password" required>'
        . '<label for="n">Nové heslo (aspoň ' . Admin::MIN_PASSWORD . ' znaků)</label><input id="n" name="new" type="password" autocomplete="new-password" minlength="' . Admin::MIN_PASSWORD . '" required>'
        . '<label for="a">Nové heslo znovu</label><input id="a" name="again" type="password" autocomplete="new-password" required>'
        . (isset($errors[$msg]) ? '<div class="err">' . h($errors[$msg]) . '</div>' : '')
        . '<button class="btn" type="submit">Změnit heslo</button><a class="back" href="./">Zpět na návštěvy</a></form></main>';
    page('Změna hesla · Orbit', $body);
}

// ---------------------------------------------------------------- data

$now = time();
$from = strtotime('-' . ($days - 1) . ' days', strtotime('today', $now));
$prevFrom = strtotime('-' . $days . ' days', $from);
$prevTo = strtotime('-' . $days . ' days', $now);
$recs = Stats::records($prevFrom, $now + 1);
$cur = $prev = [];
foreach ($recs as $r) {
    if ($r['t'] >= $from) {
        $cur[] = $r;
    } elseif ($r['t'] < $prevTo) {
        $prev[] = $r;
    }
}
$res = Stats::visits($cur, $now);
$visits = $res['visits'];
$left = $res['left_out'];
$t = tally($visits);
$p = tally(Stats::visits($prev, $now)['visits']);
$pageVisits = array_values(array_filter($visits, static function (array $v): bool {
    return !$v['only_cmd'];
}));
$beforeWhat = $days === 1 ? 'včerejšku touhle dobou' : $days . ' dnům předtím';

// ---------------------------------------------------------------- headline

$sources = counts($visits, static function (array $v) {
    return $v['source'];
});
$periodWords = $days === 1 ? 'Dnes' : 'Za posledních ' . $days . ' dní';
if ($t['people'] === 0 && $t['install'] === 0) {
    $sum = $periodWords . ' na web nepřišel nikdo, kdo by si ho opravdu prohlížel.';
} else {
    $sum = $periodWords . ': <b>' . $t['people'] . ' ' . plural($t['people'], 'člověk', 'lidé', 'lidí') . '</b> na webu'
        . ', <b>' . $t['download'] . '</b> ' . plural($t['download'], 'stažení', 'stažení', 'stažení') . ' instalátoru'
        . ', <b>' . $t['install'] . '</b> ' . plural($t['install'], 'instalace', 'instalace', 'instalací') . ' příkazem'
        . ' a <b>' . $t['copy'] . '</b> ' . plural($t['copy'], 'zkopírované zadání', 'zkopírovaná zadání', 'zkopírovaných zadání') . '.';
    if ($sources && $t['people'] >= 3) {
        $topSource = (string)array_key_first($sources);
        $sum .= ' Nejvíc lidí přišlo ' . ($topSource === 'Přímo' ? 'přímo (bez odkazu)' : 'odtud: <b>' . h($topSource) . '</b>')
            . ' (' . $sources[$topSource] . ').';
    }
}
$flash = ['forgot' => 'Návštěva je pryč ze statistik.', 'nothing' => 'Nebylo co smazat (návštěva už v datech není).',
    'password' => 'Heslo je změněné. Ostatní prohlížeče jsou odhlášené.'];

$html = $top . '<main class="wrap"><section class="hero"><h1>Kdo byl na webu</h1><p class="sum">' . $sum . '</p>'
    . (isset($flash[$msg]) ? '<p class="flash">' . h($flash[$msg]) . '</p>' : '')
    . '<div class="tiles">'
    . '<div class="tile"><div class="lbl"><i></i>Lidé na webu</div><div class="val">' . $t['people'] . '</div><div class="dl">' . delta($t['people'], $p['people'], $beforeWhat) . '</div></div>'
    . '<div class="tile" style="--k:var(--done)"><div class="lbl"><i></i>Stažení instalátoru</div><div class="val">' . $t['download'] . '</div><div class="dl">' . delta($t['download'], $p['download'], $beforeWhat) . '</div></div>'
    . '<div class="tile" style="--k:var(--done)"><div class="lbl"><i></i>Instalace příkazem</div><div class="val">' . $t['install'] . '</div><div class="dl">Claude Code nebo PowerShell</div></div>'
    . '<div class="tile"><div class="lbl"><i></i>Zkopírované zadání</div><div class="val">' . $t['copy'] . '</div><div class="dl">pro Clauda nebo PowerShell</div></div>'
    . '<div class="tile live" style="--k:var(--done)"><div class="lbl"><i></i>Teď na webu</div><div class="val">' . ($t['live'] ? '<span class="pulse"></span>' : '') . $t['live'] . '</div><div class="dl">' . ($t['live'] ? 'právě si web prohlíží' : 'nikdo') . '</div></div>'
    . '</div></section>';

// ---------------------------------------------------------------- day by day (or hour by hour today)

$buckets = [];
if ($days === 1) {
    for ($hh = 0; $hh <= (int)date('G', $now); $hh++) {
        $buckets[sprintf('%02d', $hh)] = [0, 0, $hh . ':00'];
    }
} else {
    for ($d = $from; $d <= $now; $d = strtotime('+1 day', $d)) {
        $buckets[date('Y-m-d', $d)] = [0, 0, dayLabel($d, $now)];
    }
}
foreach ($pageVisits as $v) {
    $k = $days === 1 ? date('H', $v['t0']) : date('Y-m-d', $v['t0']);
    if (!isset($buckets[$k])) {
        continue;
    }
    if (in_array($v['result'], CONVERTED, true) || $v['run']) {
        $buckets[$k][0]++;
    } else {
        $buckets[$k][1]++;
    }
}
$peak = 1;
foreach ($buckets as $b) {
    $peak = max($peak, $b[0] + $b[1]);
}
$cols = '';
$table = '';
foreach ($buckets as $b) {
    $all = $b[0] + $b[1];
    $tip = $b[2] . '|' . $all . ' ' . plural($all, 'návštěva', 'návštěvy', 'návštěv') . ($b[0] ? ', ' . $b[0] . ' se stažením nebo instalací' : '');
    $cols .= '<div class="col" tabindex="0" data-tip="' . h($tip) . '" aria-label="' . h(str_replace('|', ': ', $tip)) . '">'
        . ($b[0] ? '<i class="a" style="height:' . round($b[0] / $peak * 100, 2) . '%"></i>' : '')
        . ($b[1] ? '<i style="height:' . round($b[1] / $peak * 100, 2) . '%"></i>' : '') . '</div>';
    $table .= '<tr><th>' . h($b[2]) . '</th><td>' . $all . '</td><td>' . $b[0] . '</td></tr>';
}
$labels = array_column($buckets, 2);
$axis = '<span>' . h((string)reset($labels)) . '</span>' . (count($labels) > 2 ? '<span>' . h((string)$labels[intdiv(count($labels), 2)]) . '</span>' : '')
    . '<span>' . h((string)end($labels)) . '</span>';
$html .= '<section class="card chart"><div class="head"><h2>' . ($days === 1 ? 'Dnes po hodinách' : 'Den po dni') . '</h2>'
    . '<ul class="legend"><li><i class="k1"></i>se stažením nebo instalací</li><li><i></i>ostatní návštěvy</li></ul></div>'
    . '<div class="plot"><div class="grid" style="top:0"><span>' . $peak . '</span></div>' . $cols . '</div><div class="axis">' . $axis . '</div>'
    . '<div class="sr"><table><caption>Návštěvy ' . ($days === 1 ? 'po hodinách' : 'po dnech') . '</caption><tr><th>' . ($days === 1 ? 'Hodina' : 'Den')
    . '</th><th>Návštěvy</th><th>Se stažením nebo instalací</th></tr>' . $table . '</table></div></section>';

// ---------------------------------------------------------------- who came

$limit = max(30, min(500, (int)($_GET['n'] ?? 60)));
$list = '';
$shown = 0;
$byDay = [];
foreach ($visits as $v) {
    $byDay[date('Y-m-d', $v['t0'])][] = $v;
}
foreach ($byDay as $dayVisits) {
    $full = $briefs = [];
    foreach ($dayVisits as $v) {
        if ($v['result'] === 'brief' && !$v['live']) {
            $briefs[] = $v;
        } else {
            $full[] = $v;
        }
    }
    if ($shown >= $limit) {
        break;
    }
    $list .= '<div class="day"><h3>' . h(dayLabel($dayVisits[0]['t0'], $now)) . ' · ' . count($dayVisits) . ' ' . plural(count($dayVisits), 'návštěva', 'návštěvy', 'návštěv') . '</h3>';
    foreach ($full as $v) {
        if ($shown++ >= $limit) {
            break;
        }
        [$resLabel, $resIcon] = RESULTS[$v['result']];
        $who = [];
        if ($v['only_cmd']) {
            $who[] = '<span>' . icon('terminal') . 'jen příkaz, stránku si z této sítě nikdo neotevřel</span>';
        } else {
            $who[] = '<span>' . ($v['country'] ? '<span class="cc">' . h($v['country']) . '</span>' : icon('pin')) . h(country($v['country']))
                . ($v['city'] ? ', ' . h($v['city']) : '') . '</span>';
            $who[] = '<span>' . icon('device') . h(machine($v)) . ($v['browser'] ? ' · ' . h($v['browser']) : '') . '</span>';
            $lang = language($v['lang']);
            if ($lang !== null && $v['lang'] !== 'cs') {
                $who[] = '<span>' . icon('lang') . h($lang) . '</span>';
            }
            $who[] = '<span class="src"' . ($v['referrer'] ? ' title="' . h($v['referrer']) . '"' : '') . '>' . icon('from') . h($v['source'])
                . ($v['arrived_at'] && isset(Stats::SECTIONS[$v['arrived_at']]) ? ' <span style="color:var(--dim)">· rovnou na ' . h(Stats::SECTIONS[$v['arrived_at']]) . '</span>' : '') . '</span>';
            if ($v['loads'] > 1) {
                $who[] = '<span>' . $v['loads'] . '× načtená stránka</span>';
            }
        }
        if ($v['only_cmd'] && $v['country']) {
            $who[] = '<span><span class="cc">' . h($v['country']) . '</span>' . h(country($v['country'])) . '</span>';
        }
        $path = '';
        foreach (steps($v) as $i => $s) {
            $ic = $s[0] === 'good' ? icon(strpos($s[1], 'Stažení') === 0 ? 'download' : (strpos($s[1], 'Zkop') !== false || strpos($s[1], 'zkop') !== false ? 'copy' : 'terminal')) : '';
            $path .= ($i ? '<li class="sep" aria-hidden="true">›</li>' : '') . '<li class="' . $s[0] . '">' . $ic . h($s[1]) . ($s[2] !== '' ? ' <em>' . h($s[2]) . '</em>' : '') . '</li>';
        }
        $list .= '<article class="visit r-' . $v['result'] . '"><div class="v-head"><time datetime="' . date('c', $v['t0']) . '">' . date('G:i', $v['t0']) . '</time>'
            . '<span class="dur">' . ($v['only_cmd'] ? '' : h(dur($v['duration'])) . ' na stránce') . '</span>'
            . ($v['live'] ? '<span class="now"><span class="pulse"></span>teď na webu</span>' : '')
            . '<span class="res">' . icon($resIcon) . h($resLabel) . '</span></div>'
            . '<div class="v-who">' . implode('', $who) . '</div>'
            . ($path !== '' ? '<ol class="path">' . $path . '</ol>' : '')
            . '<div class="v-foot"><form method="post" action="' . h($self) . '"><input type="hidden" name="csrf" value="' . h($csrf) . '">'
            . '<input type="hidden" name="action" value="forget"><input type="hidden" name="ids" value="' . h(implode(',', $v['ids'])) . '">'
            . '<input type="hidden" name="t0" value="' . $v['t0'] . '"><input type="hidden" name="t1" value="' . $v['t1'] . '">'
            . '<button class="forget" type="submit" data-sure="Opravdu smazat ze statistik?">To jsem byl já</button></form></div></article>';
    }
    if ($briefs) {
        $list .= '<details class="brief"><summary>a ' . count($briefs) . ' ' . plural(count($briefs), 'krátká návštěva', 'krátké návštěvy', 'krátkých návštěv')
            . ' jen s úvodem (pod 30 s)</summary><ul>';
        foreach ($briefs as $v) {
            $list .= '<li>' . date('G:i', $v['t0']) . ' · ' . h(dur($v['duration'])) . ' · ' . h(country($v['country'])) . ' · ' . h(machine($v)) . ' · ' . h($v['source']) . '</li>';
        }
        $list .= '</ul></details>';
    }
    $list .= '</div>';
}
if ($list === '') {
    $list = '<div class="empty"><b>Zatím tu nikdo není</b>Návštěvy se ukážou, jak někdo otevře orbit.easya.cz a začne si stránku prohlížet.</div>';
} elseif ($shown > $limit) {
    $list .= '<a class="more" href="./?d=' . $days . '&amp;n=' . ($limit + 100) . '">Ukázat další návštěvy</a>';
}

$leftNote = '';
if ($left['robots'] || $left['unseen']) {
    $parts = [];
    if ($left['robots']) {
        $parts[] = $left['robots'] . ' ' . plural($left['robots'], 'robot', 'roboti', 'robotů');
    }
    if ($left['unseen']) {
        $parts[] = $left['unseen'] . ' ' . plural($left['unseen'], 'otevření', 'otevření', 'otevření') . ' bez prohlížení';
    }
    $leftNote = 'Vynecháno: ' . implode(' a ', $parts) . '.';
}
$html .= '<div class="grid-main"><section class="card visits"><h2>Kdo přišel <small>nejnovější nahoře</small></h2>'
    . '<p class="note">Jen lidé, kteří stránku opravdu měli na obrazovce a scrollovali, hýbali myší nebo klikli. ' . h($leftNote) . '</p>'
    . $list . '</section><aside>';

// ---------------------------------------------------------------- the path through the page

$steps = [
    ['Přišli na web', $t['people']],
    ['Podívali se dál než na úvod', $t['explored']],
    ['Došli až k instalaci', $t['reached']],
    ['Stáhli, zkopírovali nebo spustili instalaci', $t['converted']],
];
$funnel = '<ol class="funnel">';
$worst = null;
for ($i = 1; $i < count($steps); $i++) {
    $loss = $steps[$i - 1][1] - $steps[$i][1];
    if ($loss > 0 && ($worst === null || $loss > $worst[1])) {
        $worst = [$i, $loss];
    }
}
foreach ($steps as $i => $s) {
    $funnel .= '<li><div class="row"><b>' . $s[1] . '</b><span>' . h($s[0]) . '</span></div>'
        . '<div class="b"><i style="width:' . ($t['people'] ? max(1, round($s[1] / $t['people'] * 100)) : 0) . '%"></i></div>';
    if ($i < count($steps) - 1) {
        $loss = $s[1] - $steps[$i + 1][1];
        $funnel .= '<div class="loss' . ($worst && $worst[0] === $i + 1 ? ' big' : '') . '">' . ($loss > 0 ? '− ' . $loss . ' odešlo' : 'nikdo neodešel') . '</div>';
    }
    $funnel .= '</li>';
}
$funnel .= '</ol>';
$hint = '';
if ($worst && $t['people'] >= 3) {
    $hints = [
        1 => 'Nejvíc lidí odchází hned z úvodu: video a první obrazovka je nezaujmou natolik, aby scrollovali dál.',
        2 => 'Nejvíc lidí si prohlédne funkce, ale k instalaci už nedojde.',
        3 => 'Nejvíc lidí dojde k instalaci, ale nic nestáhne ani nezkopíruje.',
    ];
    $hint = '<p class="note">' . h($hints[$worst[0]]) . '</p>';
}
$html .= '<section class="card"><h2>Cesta po stránce</h2>' . $funnel . $hint
    . ($t['install'] > $t['converted'] ? '<p class="note">Instalací příkazem je víc: někdo spustil příkaz bez návštěvy stránky (třeba z GitHubu nebo podle zadání od někoho jiného).</p>' : '')
    . '</section>';

// ---------------------------------------------------------------- where from, who

$html .= '<section class="card"><h2>Odkud přišli</h2>' . bars($sources) . '</section>';
$html .= '<section class="card"><h2>Země</h2>' . bars(counts($visits, static function (array $v) {
    return $v['country'] ?? '?';
}), 8, static function (string $c): string {
    return $c === '?' ? 'neznámá země' : country($c);
}) . '</section>';
$machines = counts($visits, static function (array $v) {
    return machine($v);
});
$html .= '<section class="card"><h2>Na čem</h2>' . bars($machines)
    . '<p class="note">Orbit jde nainstalovat jen na Windows: ' . $t['windows'] . ' z ' . $t['people'] . ' ' . plural($t['people'], 'návštěvy', 'návštěv', 'návštěv') . ' bylo z Windows.</p>'
    . '<p class="sub">Prohlížeč</p>' . bars(counts($visits, static function (array $v) {
        return $v['browser'];
    }), 5) . '</section>';

// ---------------------------------------------------------------- what interested them

$reach = $times = [];
foreach ($pageVisits as $v) {
    foreach ($v['sections'] as $name => $sec) {
        $reach[$name] = ($reach[$name] ?? 0) + 1;
        $times[$name][] = (int)$sec[0];
    }
}
$sectionCounts = [];
$sectionNotes = [];
foreach (Stats::SECTIONS as $name => $label) {
    if (isset($reach[$name])) {
        $sectionCounts[$name] = $reach[$name];
        $typical = median($times[$name]);
        $sectionNotes[$name] = $typical < 1000 ? 'obvykle jen průjezdem' : 'obvykle ' . dur(intdiv($typical, 1000));
    }
}
$html .= '<section class="card"><h2>Co si prohlédli <small>kolik lidí došlo k části stránky</small></h2>'
    . bars($sectionCounts, 9, static function (string $k): string {
        return Stats::SECTIONS[$k];
    }, $sectionNotes);
$features = counts($visits, static function (array $v): array {
    $out = [];
    foreach ($v['items'] as $it) {
        if ($it[1] === 'ev' && $it[2]['e'] === 'feature' && isset(Stats::FEATURES[$it[2]['m'] ?? ''])) {
            $out[] = Stats::FEATURES[$it[2]['m']];
        }
    }
    return array_unique($out);
});
$faq = counts($visits, static function (array $v): array {
    $out = [];
    foreach ($v['items'] as $it) {
        if ($it[1] === 'ev' && $it[2]['e'] === 'faq' && ($it[2]['m'] ?? '') !== '') {
            $out[] = $it[2]['m'];
        }
    }
    return array_unique($out);
});
$sound = $demo = 0;
$soundTimes = [];
foreach ($pageVisits as $v) {
    if ($v['video']['sound'] > 0) {
        $sound++;
        $soundTimes[] = $v['video']['sound'];
    }
    $demo += $v['demo'] > 0 ? 1 : 0;
}
$html .= '<p class="sub">Funkce v panelu</p>' . bars($features, 9)
    . '<p class="sub">Otázky</p>' . bars($faq, 6)
    . '<p class="note">Video se zvukem si pustilo ' . $sound . ' ' . plural($sound, 'člověk', 'lidé', 'lidí')
    . ($sound ? ' (obvykle ' . dur(median($soundTimes)) . ')' : '') . ', ukázku diktování zkusilo ' . $demo . '.</p></section>';
$places = counts($visits, static function (array $v): array {
    $out = [];
    foreach ($v['items'] as $it) {
        if ($it[1] === 'ev' && $it[2]['e'] === 'download') {
            $out[] = 'tlačítko ' . (Stats::PLACES[$it[2]['m'] ?? ''] ?? 'jinde');
        }
    }
    return $out;
});
$html .= '<section class="card"><h2>Odkud stahují</h2>' . bars($places) . '</section></aside></div>';

// ---------------------------------------------------------------- footer

$viaCf = Stats::viaCloudflare();
$myCountry = Stats::country();
$ownerNet = in_array(Stats::clientIp(), Stats::ownerIps(), true);
$html .= '<footer class="foot">'
    . '<div><b>Tvoje návštěvy se neměří:</b> tenhle prohlížeč je po přihlášení vyřazený' . ($ownerNet ? ' a síť, ze které se díváš, taky' : '') . '. Co se přesto zapíše (třeba z mobilu na datech), smaže „To jsem byl já“.</div>'
    . '<div><b>Soukromí návštěvníků:</b> žádné cookies, IP adresa se neukládá (jen otisk, který se každý den mění), nic se neposílá jinam. Data se drží ' . Stats::KEEP_DAYS . ' dní. Kdo má v prohlížeči zapnuté Nesledovat, nepočítá se vůbec.</div>'
    . '<div><b>Země:</b> ' . ($viaCf ? 'posílá Cloudflare' . ($myCountry ? ' (tvoje: ' . h(country($myCountry)) . ')' : ', ale bez země: zapni v Cloudflare IP Geolocation') : 'požadavek nepřišel přes Cloudflare, země se nepozná')
    . (Stats::city() !== null ? ', i s městem' : '. Město přidá v Cloudflare Rules › Managed Transforms „Add visitor location headers“') . '.</div>'
    . '<div><a href="./?heslo=1">Změnit heslo</a></div></footer></main>';

page('Návštěvy · Orbit', $html, true);
