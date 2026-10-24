<?php
/**
 * Login for /admin/: one password, stored only as a PBKDF2 hash in data/admin.php (web/publish.py --admin-password
 * makes it, the admin page can change it), a cookie signed with the server's key, and at most 5 wrong passwords per
 * network in 15 minutes and 20 from anywhere in an hour. Logging in also stops measuring that browser.
 */
declare(strict_types=1);

require_once __DIR__ . '/stats.php';

final class Admin
{
    public const COOKIE_DAYS = 30;
    public const MIN_PASSWORD = 12;
    public const ITERATIONS = 400000;

    public static function cookieName(): string
    {
        return Stats::dev() ? 'orbit_admin' : '__Host-orbit-admin';
    }

    public static function account(): ?array
    {
        $a = Stats::readGuarded(Stats::dir() . '/admin.php');
        if (!is_array($a) || !preg_match('/^[0-9a-f]{32,}$/', (string)($a['salt'] ?? ''))
            || !preg_match('/^[0-9a-f]{64}$/', (string)($a['hash'] ?? '')) || (int)($a['iter'] ?? 0) < 100000) {
            return null;
        }
        return $a;
    }

    public static function verify(string $password): bool
    {
        $a = self::account();
        if ($a === null || $password === '' || strlen($password) > 200) {
            return false;
        }
        $calc = hash_pbkdf2('sha256', $password, (string)hex2bin($a['salt']), (int)$a['iter'], 32, true);
        return hash_equals((string)hex2bin($a['hash']), $calc);
    }

    public static function setPassword(string $password): bool
    {
        $salt = random_bytes(16);
        return Stats::writeGuarded(Stats::dir() . '/admin.php', [
            'salt' => bin2hex($salt), 'iter' => self::ITERATIONS, 'set' => time(),
            'hash' => bin2hex(hash_pbkdf2('sha256', $password, $salt, self::ITERATIONS, 32, true)),
        ]);
    }

    /** Changes with the password, so a new password logs every other browser out. */
    private static function version(array $a): string
    {
        return substr(hash('sha256', $a['salt'] . $a['hash']), 0, 12);
    }

    private static function sign(string $data): string
    {
        return hash_hmac('sha256', 'admin|' . $data, Stats::key());
    }

    public static function loggedIn(): bool
    {
        $c = $_COOKIE[self::cookieName()] ?? '';
        $parts = is_string($c) ? explode('.', $c) : [];
        if (count($parts) !== 3 || !ctype_digit($parts[0]) || (int)$parts[0] < time()) {
            return false;
        }
        $a = self::account();
        return $a !== null && hash_equals(self::version($a), $parts[1])
            && hash_equals(self::sign($parts[0] . '.' . $parts[1]), $parts[2]);
    }

    private static function cookie(string $name, string $value, int $expires, string $sameSite): void
    {
        setcookie($name, $value, [
            'expires' => $expires, 'path' => '/', 'secure' => !Stats::dev(), 'httponly' => true, 'samesite' => $sameSite,
        ]);
        $_COOKIE[$name] = $value;
    }

    public static function logIn(): void
    {
        $a = self::account();
        if ($a === null) {
            return;
        }
        $exp = (string)(time() + self::COOKIE_DAYS * 86400);
        $ver = self::version($a);
        self::cookie(self::cookieName(), $exp . '.' . $ver . '.' . self::sign($exp . '.' . $ver), (int)$exp, 'Strict');
        self::cookie(Stats::NO_STATS_COOKIE, '1', time() + 365 * 86400, 'Lax');
    }

    public static function logOut(): void
    {
        self::cookie(self::cookieName(), '', time() - 3600, 'Strict');
    }

    public static function csrf(): string
    {
        return substr(self::sign('csrf|' . (string)($_COOKIE[self::cookieName()] ?? '')), 0, 32);
    }

    public static function csrfOk($token): bool
    {
        return is_string($token) && hash_equals(self::csrf(), $token);
    }

    /** POSTs only from the admin page itself (the auth cookie is SameSite=Strict as well). */
    public static function sameOrigin(): bool
    {
        if (Stats::dev()) {
            return true;
        }
        $src = (string)($_SERVER['HTTP_ORIGIN'] ?? '');
        if ($src === '' || $src === 'null') {
            $src = (string)($_SERVER['HTTP_REFERER'] ?? '');
        }
        return strtolower((string)parse_url($src, PHP_URL_HOST)) === 'orbit.easya.cz'
            && strtolower((string)parse_url($src, PHP_URL_SCHEME)) === 'https';
    }

    // ---------------------------------------------------------------- wrong passwords

    private static function triesPath(): string
    {
        return Stats::dir() . '/login.php';
    }

    private static function network(): string
    {
        return Stats::hashes(Stats::clientIp(), '')['ih'];
    }

    /** null = may try, else seconds to wait. */
    public static function lockedFor(): ?int
    {
        $tries = (array)(Stats::readGuarded(self::triesPath())['tries'] ?? []);
        $now = time();
        $mine = $all = [];
        foreach ($tries as $t) {
            if (!is_array($t) || count($t) !== 2) {
                continue;
            }
            if ($t[0] > $now - 3600) {
                $all[] = (int)$t[0];
            }
            if ($t[1] === self::network() && $t[0] > $now - 900) {
                $mine[] = (int)$t[0];
            }
        }
        if (count($mine) >= 5) {
            return max(60, min($mine) + 900 - $now);
        }
        if (count($all) >= 20) {
            return max(60, min($all) + 3600 - $now);
        }
        return null;
    }

    public static function failed(): void
    {
        $tries = (array)(Stats::readGuarded(self::triesPath())['tries'] ?? []);
        $now = time();
        $tries = array_values(array_filter($tries, static function ($t) use ($now): bool {
            return is_array($t) && count($t) === 2 && $t[0] > $now - 3600;
        }));
        $tries[] = [$now, self::network()];
        Stats::writeGuarded(self::triesPath(), ['tries' => array_slice($tries, -200)]);
    }
}
