<?php
/**
 * Orbit's own visit statistics for orbit.easya.cz: what api/hit.php collects, what api/serve.php counts and what
 * admin/index.php shows. Not reachable over HTTP (lib/.htaccess, and the root .htaccess denies every other PHP file).
 *
 * Visitors get no cookie and nothing is stored in their browser: assets/visit.js keeps one random id per page load in
 * memory. IP addresses are never stored: only two HMACs that change every day (the same browser on the same network;
 * the same network), so visits can't be linked across days. Nothing goes to anyone else. Written for PHP 7.4+.
 */
declare(strict_types=1);

date_default_timezone_set('Europe/Prague');

final class Stats
{
    public const ORIGIN = 'https://orbit.easya.cz';
    public const KEEP_DAYS = 400;
    /** A new visit after 30 minutes without a sign of life from the same browser. */
    public const GAP_S = 1800;
    /** "On the web now": a heartbeat in the last 2 minutes (visit.js sends one every 30 s while the page is seen). */
    public const LIVE_S = 120;
    /** Seen this long without scrolling, moving the mouse or clicking still counts as a visit. */
    public const SEEN_MS = 8000;
    /** A day's file stops growing here (somebody flooding the endpoint must not fill the hosting). */
    public const MAX_DAY_BYTES = 20000000;
    /** Beacons from one network per 10 minutes (a long visit with lots of clicking sends about 60). */
    public const RATE_PER_IP = 240;
    /** The owner's networks (as ANALYTICS_IGNORE_IPS on m-tex.cz) are in data/owner.php, written by publish.py from a
     * file outside the repository (it is public): the owner's own visits are not measured. */
    public const OWNER_FILE = 'owner.php';
    /** Set for a year by logging into the admin: this browser is not measured either. */
    public const NO_STATS_COOKIE = 'orbit_no_stats';

    public const EVENTS = ['download', 'copy', 'script_view', 'github', 'link', 'video_sound', 'demo', 'feature', 'faq', 'theme'];

    /** Parts of the page, in page order (ids of the sections in index.html). */
    public const SECTIONS = [
        'top' => 'Úvod a video', 'povely' => 'Povely', 'diktovani' => 'Diktování', 'soukromi' => 'Soukromí',
        'claude' => 'Claude Code', 'pozadavky' => 'Požadavky', 'instalace' => 'Instalace', 'otazky' => 'Otázky',
        'konec' => 'Závěr',
    ];

    public const FEATURES = [
        'limity' => 'Limity', 'relace' => 'Relace', 'poznamky' => 'Poznámky a úkoly', 'bubliny' => 'Bubliny',
        'artefakty' => 'Artefakty', 'agent' => 'Hlasový agent', 'chrome' => 'Stránky z prohlížeče',
        'verze' => 'Verze Claude Code', 'zbalit' => 'Zbalit do ikonky', 'kontrola' => 'Kontrola přepisu',
    ];

    /** Where on the page a download or GitHub button was. */
    public const PLACES = [
        'menu' => 'v menu', 'uvod' => 'v úvodu', 'video' => 've videu', 'instalace' => 'v instalaci',
        'otazky' => 'v otázkách', 'konec' => 'na konci', 'paticka' => 'v patičce', 'jinde' => 'jinde', 'issues' => 'Issues',
    ];

    private const GUARD = "<?php exit; ?>\n";

    // Cloudflare's published ranges (cloudflare.com/ips): only from these is CF-Connecting-IP the visitor.
    private const CF_V4 = [
        '173.245.48.0/20', '103.21.244.0/22', '103.22.200.0/22', '103.31.4.0/22', '141.101.64.0/18',
        '108.162.192.0/18', '190.93.240.0/20', '188.114.96.0/20', '197.234.240.0/22', '198.41.128.0/17',
        '162.158.0.0/15', '104.16.0.0/13', '104.24.0.0/14', '172.64.0.0/13', '131.0.72.0/22',
    ];
    private const CF_V6 = [
        '2400:cb00::/32', '2606:4700::/32', '2803:f800::/32', '2405:b500::/32', '2405:8100::/32',
        '2a06:98c0::/29', '2c0f:f248::/32',
    ];

    // ---------------------------------------------------------------- storage

    /** Local tests run with ORBIT_STATS_DEV=1 (php -S over http, any origin, readable cookie names). */
    public static function dev(): bool
    {
        return getenv('ORBIT_STATS_DEV') === '1';
    }

    public static function dir(): string
    {
        $dir = (string)getenv('ORBIT_STATS_DATA');
        return rtrim($dir !== '' ? $dir : dirname(__DIR__) . '/data', '/\\');
    }

    /** The data folder, and the .htaccess that keeps it off the web even if the upload of it got lost. */
    public static function ensureDir(): void
    {
        $dir = self::dir();
        if (!is_dir($dir)) {
            @mkdir($dir, 0700, true);
        }
        if (!is_file($dir . '/.htaccess')) {
            @file_put_contents($dir . '/.htaccess', "Require all denied\n");
        }
    }

    /** JSON behind a PHP guard line: served by mistake, the file prints nothing. */
    public static function readGuarded(string $path): ?array
    {
        $raw = @file_get_contents($path);
        $guard = rtrim(self::GUARD);
        if (!is_string($raw) || strncmp($raw, $guard, strlen($guard)) !== 0) {
            return null;
        }
        $data = json_decode(substr($raw, strlen($guard)), true);  // also with \r\n after the guard (edited over FTP)
        return is_array($data) ? $data : null;
    }

    public static function writeGuarded(string $path, array $data): bool
    {
        self::ensureDir();
        $tmp = $path . '.' . bin2hex(random_bytes(4)) . '.tmp';
        $json = json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_INVALID_UTF8_SUBSTITUTE);
        if ($json === false || @file_put_contents($tmp, self::GUARD . $json) === false) {
            @unlink($tmp);
            return false;
        }
        if (!@rename($tmp, $path)) {
            @unlink($tmp);
            return false;
        }
        return true;
    }

    /** The server's own secret (made on first use): keys the daily hashes, the admin cookie and the CSRF token. */
    public static function key(): string
    {
        static $key = null;
        if ($key !== null) {
            return $key;
        }
        $path = self::dir() . '/secret.php';
        $data = self::readGuarded($path);
        if (!is_array($data)) {
            self::ensureDir();
            $f = @fopen($path, 'x');  // the first request wins; a second one reads what the first wrote
            if ($f) {
                fwrite($f, self::GUARD . json_encode(['key' => bin2hex(random_bytes(32))]));
                fclose($f);
            } else {
                usleep(50000);
            }
            $data = self::readGuarded($path);
        }
        $hex = is_array($data) ? (string)($data['key'] ?? '') : '';
        if (!preg_match('/^[0-9a-f]{64}$/', $hex)) {
            throw new RuntimeException('Orbit stats: no secret key');
        }
        return $key = (string)hex2bin($hex);
    }

    private static function dayFile(string $day): string
    {
        return self::dir() . '/hits-' . $day . '.php';
    }

    public static function append(array $rec): void
    {
        self::ensureDir();
        $line = json_encode($rec, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_INVALID_UTF8_SUBSTITUTE);
        if ($line === false) {
            return;
        }
        $f = @fopen(self::dayFile(date('Y-m-d', (int)$rec['t'])), 'c');
        if (!$f) {
            return;
        }
        if (flock($f, LOCK_EX)) {
            $size = (int)(fstat($f)['size'] ?? 0);
            if ($size < self::MAX_DAY_BYTES) {
                fseek($f, 0, SEEK_END);
                fwrite($f, ($size === 0 ? self::GUARD : '') . $line . "\n");
                fflush($f);
            }
            flock($f, LOCK_UN);
        }
        fclose($f);
        if (mt_rand(1, 400) === 1) {
            self::prune();
        }
    }

    /** Days older than KEEP_DAYS go. */
    public static function prune(): void
    {
        $limit = date('Y-m-d', time() - self::KEEP_DAYS * 86400);
        foreach (glob(self::dir() . '/hits-*.php') ?: [] as $path) {
            if (preg_match('/hits-(\d{4}-\d{2}-\d{2})\.php$/', $path, $m) && $m[1] < $limit) {
                @unlink($path);
            }
        }
    }

    /** Everything recorded in [from, to). */
    public static function records(int $from, int $to): array
    {
        $out = [];
        for ($day = strtotime(date('Y-m-d 00:00:00', $from)); $day < $to; $day = strtotime('+1 day', $day)) {
            $raw = @file_get_contents(self::dayFile(date('Y-m-d', $day)));
            if (!is_string($raw)) {
                continue;
            }
            foreach (explode("\n", $raw) as $line) {
                if ($line === '' || $line[0] !== '{') {
                    continue;
                }
                $r = json_decode($line, true);
                if (is_array($r) && isset($r['t'], $r['id'], $r['k']) && $r['t'] >= $from && $r['t'] < $to) {
                    $out[] = $r;
                }
            }
        }
        return $out;
    }

    /** "That was me": the page loads (and installer fetches) of a visit disappear from the day files. */
    public static function forget(array $ids, int $from, int $to): int
    {
        $ids = array_flip(array_filter($ids, static function ($id): bool {
            return is_string($id) && preg_match('/^s?[0-9a-f]{19,20}$/', $id) === 1;
        }));
        if (!$ids) {
            return 0;
        }
        $gone = 0;
        for ($day = strtotime(date('Y-m-d 00:00:00', $from)); $day < $to; $day = strtotime('+1 day', $day)) {
            $f = @fopen(self::dayFile(date('Y-m-d', $day)), 'r+');
            if (!$f) {
                continue;
            }
            if (flock($f, LOCK_EX)) {
                $keep = [];
                $lines = explode("\n", (string)stream_get_contents($f));
                foreach ($lines as $line) {
                    if ($line === '') {
                        continue;
                    }
                    $r = $line[0] === '{' ? json_decode($line, true) : null;
                    if (is_array($r) && isset($ids[(string)($r['id'] ?? '')])) {
                        $gone++;
                        continue;
                    }
                    $keep[] = $line;
                }
                ftruncate($f, 0);
                rewind($f);
                fwrite($f, implode("\n", $keep) . "\n");
                fflush($f);
                flock($f, LOCK_UN);
            }
            fclose($f);
        }
        return $gone;
    }

    // ---------------------------------------------------------------- who is asking

    public static function inCidr(string $ip, string $cidr): bool
    {
        [$net, $bits] = explode('/', $cidr);
        $a = @inet_pton($ip);
        $b = @inet_pton($net);
        if ($a === false || $b === false || strlen($a) !== strlen($b)) {
            return false;
        }
        $bits = (int)$bits;
        $bytes = intdiv($bits, 8);
        if (substr($a, 0, $bytes) !== substr($b, 0, $bytes)) {
            return false;
        }
        $rest = $bits % 8;
        if ($rest === 0) {
            return true;
        }
        $mask = (0xFF << (8 - $rest)) & 0xFF;
        return (ord($a[$bytes]) & $mask) === (ord($b[$bytes]) & $mask);
    }

    /** Did this request come through Cloudflare (so its headers about the visitor can be believed)? */
    public static function viaCloudflare(): bool
    {
        $ip = (string)($_SERVER['REMOTE_ADDR'] ?? '');
        foreach (strpos($ip, ':') !== false ? self::CF_V6 : self::CF_V4 as $cidr) {
            if (self::inCidr($ip, $cidr)) {
                return true;
            }
        }
        return false;
    }

    public static function clientIp(): string
    {
        if (self::viaCloudflare()) {
            $cf = (string)($_SERVER['HTTP_CF_CONNECTING_IP'] ?? '');
            if (filter_var($cf, FILTER_VALIDATE_IP)) {
                return $cf;
            }
        }
        $ip = (string)($_SERVER['REMOTE_ADDR'] ?? '');
        return filter_var($ip, FILTER_VALIDATE_IP) ? $ip : '0.0.0.0';
    }

    /** Country from Cloudflare (XX = unknown, T1 = Tor). Only statistics depend on it, so a forged one does no harm. */
    public static function country(): ?string
    {
        $c = strtoupper((string)($_SERVER['HTTP_CF_IPCOUNTRY'] ?? ''));
        return preg_match('/^[A-Z][A-Z0-9]$/', $c) && $c !== 'XX' ? $c : null;
    }

    /** City, when "Add visitor location headers" is on in Cloudflare (Rules › Managed Transforms). */
    public static function city(): ?string
    {
        $c = trim((string)($_SERVER['HTTP_CF_IPCITY'] ?? ''));
        $c = self::cleanText($c, 40);
        return $c !== '' ? $c : null;
    }

    /** Same browser on the same network today (vh), same network today (ih). IPv6 by its /64. */
    public static function hashes(string $ip, string $ua): array
    {
        if (strpos($ip, ':') !== false && ($bin = @inet_pton($ip)) !== false) {
            $ip = bin2hex(substr($bin, 0, 8));
        }
        $day = date('Y-m-d');
        $key = self::key();
        return [
            'vh' => substr(hash_hmac('sha256', "v|$day|$ip|$ua", $key), 0, 16),
            'ih' => substr(hash_hmac('sha256', "i|$day|$ip", $key), 0, 16),
        ];
    }

    /** The owner's network or a browser that logged into the admin. */
    public static function excluded(): bool
    {
        return !empty($_COOKIE[self::NO_STATS_COOKIE]) || in_array(self::clientIp(), self::ownerIps(), true);
    }

    /** @return string[] the owner's networks (data/owner.php: {"ips": [...]}), none when it is missing */
    public static function ownerIps(): array
    {
        $data = self::readGuarded(self::dir() . '/' . self::OWNER_FILE);
        $ips = is_array($data) && isset($data['ips']) && is_array($data['ips']) ? $data['ips'] : [];
        return array_values(array_filter($ips, 'is_string'));
    }

    /** Robots, link previews, test browsers and browsers too old to be a person's. Returns why, or null. */
    public static function botReason(string $ua): ?string
    {
        if ($ua === '') {
            return 'ua';
        }
        if (preg_match('/bot\b|bot[\/;)]|crawl|spider|slurp|scrap|preview|headless|lighthouse|pagespeed|gtmetrix|pingdom|uptime|monitor|'
            . 'google-|googleother|adsbot|mediapartners|bingpreview|yandex|baidu|petalbot|bytespider|gptbot|perplexity|'
            . 'facebookexternalhit|meta-externalagent|whatsapp|telegram|discord|slack|skype|embedly|iframely|'
            . 'python|curl|wget|httpclient|go-http|java\/|okhttp|axios|node-fetch|undici|phantom|selenium|puppeteer|'
            . 'playwright|cypress|electron|seo-check|orbit-check/i', $ua)) {
            return 'ua';
        }
        // scraper pools pretend to be ancient browsers (m-tex.cz audit 16 Sep 2026: Chrome 48, Firefox 3)
        if (preg_match('/Chrome\/(\d+)/', $ua, $m) && (int)$m[1] < 90) {
            return 'old';
        }
        if (preg_match('/Firefox\/(\d+)/', $ua, $m) && (int)$m[1] < 90) {
            return 'old';
        }
        if (strpos($ua, 'Mozilla/') !== 0) {
            return 'ua';
        }
        return null;
    }

    /** Device, browser, system and language of a browser request. */
    public static function visitor(string $ua): array
    {
        $d = preg_match('/iPad|Tablet|Android(?!.*Mobile)/i', $ua) ? 'tablet'
            : (preg_match('/Mobi|iPhone|iPod|Android/i', $ua) ? 'mobile' : 'desktop');
        if (preg_match('/Edg(e|A|iOS)?\//', $ua)) {
            $b = 'Edge';
        } elseif (preg_match('/OPR\/|Opera/', $ua)) {
            $b = 'Opera';
        } elseif (strpos($ua, 'SamsungBrowser') !== false) {
            $b = 'Samsung';
        } elseif (preg_match('/Firefox\/|FxiOS/', $ua)) {
            $b = 'Firefox';
        } elseif (preg_match('/Chrome\/|CriOS/', $ua)) {
            $b = 'Chrome';
        } elseif (strpos($ua, 'Safari/') !== false) {
            $b = 'Safari';
        } else {
            $b = 'jiný';
        }
        if (strpos($ua, 'Windows') !== false) {
            $o = 'Windows';
        } elseif (preg_match('/iPhone|iPad|iPod/', $ua)) {
            $o = 'iOS';
        } elseif (strpos($ua, 'Android') !== false) {
            $o = 'Android';
        } elseif (strpos($ua, 'Mac OS X') !== false) {
            $o = 'macOS';
        } elseif (strpos($ua, 'CrOS') !== false) {
            $o = 'ChromeOS';
        } elseif (strpos($ua, 'Linux') !== false) {
            $o = 'Linux';
        } else {
            $o = 'jiný';
        }
        $l = strtolower(substr((string)($_SERVER['HTTP_ACCEPT_LANGUAGE'] ?? ''), 0, 2));
        $out = ['d' => $d, 'b' => $b, 'o' => $o];
        if (preg_match('/^[a-z]{2}$/', $l)) {
            $out['l'] = $l;
        }
        return $out;
    }

    /** What fetched install.ps1 or latest.json. */
    public static function fetcher(string $ua): string
    {
        if (preg_match('/WindowsPowerShell|PowerShell\//i', $ua)) {
            return 'powershell';
        }
        if (preg_match('/Claude-User|Claude-Code|claude-cli|anthropic/i', $ua) && !preg_match('/ClaudeBot|SearchBot/i', $ua)) {
            return 'claude';
        }
        if (preg_match('/^(curl|Wget)\//i', $ua)) {
            return 'curl';
        }
        if (self::botReason($ua) !== null) {
            return 'bot';
        }
        return 'browser';
    }

    public static function cleanText($s, int $max): string
    {
        if (!is_string($s)) {
            return '';
        }
        $s = (string)preg_replace('/[^\p{L}\p{N} .,:?!\/()+#\-]/u', '', $s);
        $s = trim((string)preg_replace('/\s+/u', ' ', $s));
        return preg_match('/^.{0,' . $max . '}/us', $s, $m) ? $m[0] : '';
    }

    private static function int($v, int $min, int $max): int
    {
        return is_numeric($v) ? max($min, min($max, (int)$v)) : $min;
    }

    /** host/path of where the visitor came from; the query (search words, ids) is never kept. */
    public static function cleanReferrer($r): string
    {
        if (!is_string($r) || $r === '' || strlen($r) > 1000) {
            return '';
        }
        $p = parse_url($r);
        if (!is_array($p) || !in_array(strtolower((string)($p['scheme'] ?? '')), ['http', 'https', 'android-app'], true)) {
            return '';
        }
        $host = strtolower((string)preg_replace('/^www\./i', '', (string)($p['host'] ?? '')));
        if ($host === '' || !preg_match('/^[a-z0-9.-]{1,100}$/', $host) || $host === 'orbit.easya.cz') {
            return '';
        }
        $path = (string)preg_replace('/[^A-Za-z0-9._~\/-]/', '', (string)($p['path'] ?? ''));
        return $host . substr(rtrim($path, '/'), 0, 120);
    }

    private static function originOk(): bool
    {
        if (self::dev()) {
            return true;
        }
        $src = (string)($_SERVER['HTTP_ORIGIN'] ?? '');
        if ($src === '' || $src === 'null') {
            $src = (string)($_SERVER['HTTP_REFERER'] ?? '');
        }
        $host = strtolower((string)parse_url($src, PHP_URL_HOST));
        return $host === 'orbit.easya.cz' && strtolower((string)parse_url($src, PHP_URL_SCHEME)) === 'https';
    }

    /** At most RATE_PER_IP beacons per network per 10 minutes, counted in one small file. */
    private static function rateOk(string $ih): bool
    {
        self::ensureDir();
        $f = @fopen(self::dir() . '/rate.php', 'c+');
        if (!$f) {
            return true;
        }
        $ok = true;
        if (flock($f, LOCK_EX)) {
            $raw = (string)stream_get_contents($f);
            $data = json_decode((string)substr($raw, strlen(self::GUARD)), true);
            $data = is_array($data) ? $data : [];
            $now = time();
            $window = intdiv($now, 600);
            if (($data['w'] ?? null) !== $window) {
                $data = ['w' => $window, 'n' => []];
            }
            $n = (int)($data['n'][$ih] ?? 0);
            $ok = $n < self::RATE_PER_IP && count($data['n']) < 5000;
            if ($ok) {
                $data['n'][$ih] = $n + 1;
                ftruncate($f, 0);
                rewind($f);
                fwrite($f, self::GUARD . json_encode($data));
                fflush($f);
            }
            flock($f, LOCK_UN);
        }
        fclose($f);
        return $ok;
    }

    // ---------------------------------------------------------------- collecting

    /** One beacon from assets/visit.js (POST /api/hit.php). Anything odd is dropped without a word. */
    public static function collect(): void
    {
        if (!self::originOk() || self::excluded()) {
            return;
        }
        $in = json_decode((string)file_get_contents('php://input', false, null, 0, 4096), true);
        if (!is_array($in)) {
            return;
        }
        $id = $in['id'] ?? '';
        $k = $in['k'] ?? '';
        if (!is_string($id) || !preg_match('/^[0-9a-f]{20}$/', $id) || !in_array($k, ['start', 'ev', 'end'], true)) {
            return;
        }
        $ua = substr((string)($_SERVER['HTTP_USER_AGENT'] ?? ''), 0, 400);
        $h = self::hashes(self::clientIp(), $ua);
        if (!self::rateOk($h['ih'])) {
            return;
        }
        $rec = ['t' => time(), 'id' => $id, 'k' => $k, 'vh' => $h['vh']];
        if ($k === 'start') {
            $rec['ih'] = $h['ih'];
            $rec += self::visitor($ua);
            if (($c = self::country()) !== null) {
                $rec['c'] = $c;
            }
            if (($city = self::city()) !== null) {
                $rec['city'] = $city;
            }
            $bot = self::botReason($ua);
            if ($bot === null && !empty($in['wd'])) {
                $bot = 'wd';  // navigator.webdriver: a browser driven by a program
            }
            if ($bot !== null) {
                $rec['bot'] = $bot;
            }
            if (($r = self::cleanReferrer($in['r'] ?? '')) !== '') {
                $rec['r'] = $r;
            }
            $u = strtolower((string)($in['u'] ?? ''));
            if (preg_match('/^[a-z0-9._-]{1,40}$/', $u)) {
                $rec['u'] = $u;
            }
            $hash = (string)($in['h'] ?? '');
            if (preg_match('/^#([a-z0-9-]{1,30})$/', $hash, $m)) {
                $rec['h'] = $m[1];
            }
            $rec['cf'] = self::viaCloudflare() ? 1 : 0;
        } elseif ($k === 'ev') {
            $e = $in['e'] ?? '';
            if (!in_array($e, self::EVENTS, true)) {
                return;
            }
            $rec['e'] = $e;
            $m = self::cleanText($in['m'] ?? '', 80);
            if ($m !== '') {
                $rec['m'] = $m;
            }
            $rec['at'] = self::int($in['at'] ?? 0, 0, 86400000);
        } else {
            $s = [];
            foreach (is_array($in['s'] ?? null) ? $in['s'] : [] as $sec => $v) {
                if (is_string($sec) && isset(self::SECTIONS[$sec]) && is_array($v) && count($v) === 2) {
                    $s[$sec] = [self::int($v[0], 0, 86400000), self::int($v[1], 0, 86400000)];
                }
            }
            $rec['s'] = $s;
            $rec['vt'] = self::int($in['vt'] ?? 0, 0, 86400000);
            $rec['vs'] = self::int($in['vs'] ?? 0, 0, 86400);
            $rec['va'] = self::int($in['va'] ?? 0, 0, 86400);
            $rec['vm'] = self::int($in['vm'] ?? 0, 0, 100);
            $rec['i'] = empty($in['i']) ? 0 : 1;
            $rec['dm'] = self::int($in['dm'] ?? 0, 0, 999);
            if (!empty($in['x'])) {
                $rec['x'] = 1;  // sent as the page went away or out of sight
            }
        }
        self::append($rec);
    }

    /** install.ps1 ('script') or download/latest.json ('release') was fetched (api/serve.php). */
    public static function serverHit(string $what): void
    {
        if (self::excluded()) {
            return;
        }
        $ua = substr((string)($_SERVER['HTTP_USER_AGENT'] ?? ''), 0, 400);
        $h = self::hashes(self::clientIp(), $ua);
        if (!self::rateOk($h['ih'])) {
            return;
        }
        $rec = ['t' => time(), 'id' => 's' . substr(bin2hex(random_bytes(10)), 0, 19), 'k' => 'srv',
            'e' => $what, 'm' => self::fetcher($ua), 'vh' => $h['vh'], 'ih' => $h['ih']];
        if (($c = self::country()) !== null) {
            $rec['c'] = $c;
        }
        self::append($rec);
    }

    // ---------------------------------------------------------------- reading

    /**
     * Records → visits, newest first. A visit = page loads of one browser on one network (the same day) with less than
     * GAP_S between them, plus the installer fetches from that network around it. Robots and pages nobody looked at are
     * only counted in 'left_out'.
     */
    public static function visits(array $recs, int $now): array
    {
        usort($recs, static function (array $a, array $b): int {
            return $a['t'] <=> $b['t'];
        });
        $loads = [];
        $srv = [];
        foreach ($recs as $r) {
            if ($r['k'] === 'srv') {
                $srv[] = $r;
                continue;
            }
            $id = (string)$r['id'];
            if (!isset($loads[$id])) {
                $loads[$id] = ['id' => $id, 't0' => (int)$r['t'], 't1' => (int)$r['t'], 'start' => null, 'end' => null, 'ev' => [],
                    'vh' => (string)$r['vh'], 'gone' => false];
            }
            $L = &$loads[$id];
            $L['t1'] = max($L['t1'], (int)$r['t']);
            $L['gone'] = $r['k'] === 'end' && !empty($r['x']);  // the latest word from the page was "leaving"
            if ($r['k'] === 'start' && $L['start'] === null) {
                $L['start'] = $r;
                $L['t0'] = min($L['t0'], (int)$r['t']);
                $L['vh'] = (string)$r['vh'];
            } elseif ($r['k'] === 'end' && ($L['end'] === null || ($r['vt'] ?? 0) >= ($L['end']['vt'] ?? 0))) {
                $L['end'] = $r;
            } elseif ($r['k'] === 'ev') {
                $L['ev'][] = $r;
            }
            unset($L);
        }

        $left = ['robots' => 0, 'unseen' => 0, 'reasons' => []];
        $open = [];   // vh => index of its latest visit
        $visits = [];
        foreach ($loads as $L) {
            $bot = $L['start']['bot'] ?? null;
            if ($bot !== null) {
                $left['robots']++;
                $left['reasons'][$bot] = ($left['reasons'][$bot] ?? 0) + 1;
                continue;
            }
            $seen = (int)($L['end']['vt'] ?? 0);
            $acted = !empty($L['end']['i']) || $L['ev'];
            if (!$acted && $seen < self::SEEN_MS) {
                $left['unseen']++;
                continue;
            }
            $vh = $L['vh'];
            if (isset($open[$vh]) && $L['t0'] - $visits[$open[$vh]]['t1'] <= self::GAP_S) {
                $v = &$visits[$open[$vh]];
                $v['loads'][] = $L;
                $v['t1'] = max($v['t1'], $L['t1']);
                unset($v);
                continue;
            }
            $open[$vh] = count($visits);
            $visits[] = ['t0' => $L['t0'], 't1' => $L['t1'], 'loads' => [$L], 'srv' => [], 'ih' => (string)($L['start']['ih'] ?? '')];
        }

        // installer fetches: to the visit from the same network that was open within the hour before, else on their own
        $alone = [];
        foreach ($srv as $r) {
            if ($r['m'] === 'bot') {
                $left['robots']++;
                $left['reasons']['ua'] = ($left['reasons']['ua'] ?? 0) + 1;
                continue;
            }
            $best = null;
            foreach ($visits as $i => $v) {
                if ($v['ih'] !== '' && $v['ih'] === $r['ih'] && $r['t'] >= $v['t0'] - 600 && $r['t'] <= $v['t1'] + 3600) {
                    $best = $i;
                }
            }
            if ($best !== null) {
                $visits[$best]['srv'][] = $r;
                continue;
            }
            $key = $r['ih'];
            if (isset($alone[$key]) && $r['t'] - $visits[$alone[$key]]['t1'] <= self::GAP_S) {
                $visits[$alone[$key]]['srv'][] = $r;
                $visits[$alone[$key]]['t1'] = $r['t'];
                continue;
            }
            $alone[$key] = count($visits);
            $visits[] = ['t0' => (int)$r['t'], 't1' => (int)$r['t'], 'loads' => [], 'srv' => [$r], 'ih' => $r['ih']];
        }

        $out = array_map(static function (array $v) use ($now): array {
            return self::summarize($v, $now);
        }, $visits);
        usort($out, static function (array $a, array $b): int {
            return $b['t0'] <=> $a['t0'];
        });
        return ['visits' => $out, 'left_out' => $left];
    }

    /** One visit: who, from where, how long, what was looked at and done, in time order. */
    private static function summarize(array $v, int $now): array
    {
        $first = null;
        $live = false;
        foreach ($v['loads'] as $L) {
            if ($first === null && $L['start'] !== null) {
                $first = $L['start'];
            }
            $live = $live || (!$L['gone'] && $now - $L['t1'] <= self::LIVE_S);
        }
        $sec = [];      // section => [ms, reached at (unix ms)]
        $items = [];    // [time ms, kind, data]
        $seen = 0;
        $video = ['s' => 0, 'sound' => 0, 'max' => 0];
        $demo = 0;
        $ids = [];
        foreach ($v['loads'] as $L) {
            $ids[] = $L['id'];
            $base = $L['t0'] * 1000;
            $end = $L['end'];
            $seen += (int)($end['vt'] ?? 0);
            $video['s'] += (int)($end['vs'] ?? 0);
            $video['sound'] += (int)($end['va'] ?? 0);
            $video['max'] = max($video['max'], (int)($end['vm'] ?? 0));
            $demo += (int)($end['dm'] ?? 0);
            foreach ((array)($end['s'] ?? []) as $name => $pair) {
                if (!isset(self::SECTIONS[$name]) || !is_array($pair)) {
                    continue;
                }
                $at = $base + (int)$pair[0];
                if (!isset($sec[$name])) {
                    $sec[$name] = [0, $at];
                    $items[] = [$at, 'sec', $name];
                }
                $sec[$name][0] += (int)$pair[1];
            }
            foreach ($L['ev'] as $e) {
                $items[] = [$base + (int)($e['at'] ?? 0), 'ev', $e];
            }
        }
        foreach ($v['srv'] as $r) {
            $ids[] = $r['id'];
            $items[] = [$r['t'] * 1000, 'srv', $r];
        }
        usort($items, static function (array $a, array $b): int {
            return $a[0] <=> $b[0];
        });

        $did = [];
        foreach ($v['loads'] as $L) {
            foreach ($L['ev'] as $e) {
                $did[$e['e']] = true;
            }
        }
        $run = $ran = false;
        foreach ($v['srv'] as $r) {
            if ($r['m'] === 'powershell') {
                $run = true;
                $ran = $ran || $r['e'] === 'release';
            }
        }
        $deep = array_diff(array_keys($sec), ['top', 'povely']);
        if ($run) {
            $result = $ran ? 'install' : 'run';
        } elseif (!empty($did['download'])) {
            $result = 'download';
        } elseif (!empty($did['copy'])) {
            $result = 'copy';
        } elseif (isset($sec['instalace'])) {
            $result = 'reached';
        } elseif ($deep || $video['sound'] > 0 || count($did) > 0) {
            $result = 'browse';
        } else {
            $result = 'brief';
        }
        if ($v['loads'] === []) {
            $seen = 0;
        }
        $duration = $seen > 0 ? (int)round($seen / 1000) : max(0, $v['t1'] - $v['t0']);
        if ($result === 'brief' && $duration >= 30) {
            $result = 'browse';
        }
        return [
            't0' => $v['t0'], 't1' => $v['t1'], 'ids' => $ids, 'loads' => count($v['loads']),
            'only_cmd' => $v['loads'] === [],
            'live' => $live,
            'duration' => $duration,
            'country' => $first['c'] ?? (($v['srv'][0]['c'] ?? null)), 'city' => $first['city'] ?? null,
            'device' => $first['d'] ?? null, 'browser' => $first['b'] ?? null, 'os' => $first['o'] ?? null,
            'lang' => $first['l'] ?? null, 'cf' => $first['cf'] ?? null,
            'source' => self::source($first['r'] ?? null, $first['u'] ?? null, $v['loads'] === []),
            'referrer' => $first['r'] ?? null, 'arrived_at' => $first['h'] ?? null,
            'sections' => $sec, 'items' => $items, 'video' => $video, 'demo' => $demo,
            'did' => array_keys($did), 'run' => $run, 'ran' => $ran, 'result' => $result,
        ];
    }

    /** Where a visit came from, in words. */
    public static function source(?string $ref, ?string $utm, bool $onlyCmd = false): string
    {
        if ($onlyCmd) {
            return 'Příkaz bez návštěvy stránky';
        }
        $host = $ref !== null ? strtolower((string)strtok($ref, '/')) : '';
        // a name ending with a dot is found anywhere in the host (google.cz, mail.seznam.cz), others are the domain
        $map = [
            'mail.' => 'E-mail', 'outlook.' => 'E-mail', 'gemini.google.com' => 'Gemini', 'google.' => 'Google',
            'github.com' => 'GitHub', 'seznam.cz' => 'Seznam', 'bing.com' => 'Bing', 'duckduckgo.com' => 'DuckDuckGo',
            'chatgpt.com' => 'ChatGPT', 'openai.com' => 'ChatGPT', 'claude.ai' => 'Claude', 'perplexity.ai' => 'Perplexity',
            'facebook.com' => 'Facebook', 'fb.com' => 'Facebook', 'instagram.com' => 'Instagram', 't.co' => 'X',
            'x.com' => 'X', 'twitter.com' => 'X', 'reddit.com' => 'Reddit', 'linkedin.com' => 'LinkedIn',
            'lnkd.in' => 'LinkedIn', 'youtube.com' => 'YouTube', 'news.ycombinator.com' => 'Hacker News',
            'm-tex.cz' => 'M-tex', 'hommel-hercules.cz' => 'HHW Hommel Hercules', 'slack.com' => 'Slack',
            'discord.com' => 'Discord',
        ];
        if ($host !== '') {
            foreach ($map as $needle => $label) {
                $hit = substr($needle, -1) === '.'
                    ? strpos($host, $needle) !== false
                    : $host === $needle || substr($host, -strlen($needle) - 1) === '.' . $needle;
                if ($hit) {
                    return $label;
                }
            }
            return $host;
        }
        if ($utm !== null && $utm !== '') {
            return $utm === 'github' ? 'GitHub' : $utm;
        }
        return 'Přímo';
    }
}
