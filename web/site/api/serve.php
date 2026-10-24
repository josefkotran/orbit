<?php
/**
 * install.ps1 and download/latest.json come through here (rewrite in the root .htaccess), so the page knows when the
 * install command ran: PowerShell fetches install.ps1, then latest.json. The file always goes out first and whole;
 * counting comes after it and may fail without the install noticing.
 */
declare(strict_types=1);

$files = [
    'script' => [dirname(__DIR__) . '/install.ps1', 'text/plain; charset=utf-8'],
    'release' => [dirname(__DIR__) . '/download/latest.json', 'application/json; charset=utf-8'],
];
$what = $_GET['f'] ?? '';
if (!is_string($what) || !isset($files[$what]) || !is_file($files[$what][0])) {
    http_response_code(404);
    exit;
}
[$path, $type] = $files[$what];
header('Content-Type: ' . $type);
header('Cache-Control: no-cache');
header('Content-Length: ' . filesize($path));
if (($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'HEAD') {
    exit;
}
readfile($path);
if (function_exists('fastcgi_finish_request')) {
    fastcgi_finish_request();
}
try {
    require_once dirname(__DIR__) . '/lib/stats.php';
    Stats::serverHit($what);
} catch (Throwable $e) {
}
