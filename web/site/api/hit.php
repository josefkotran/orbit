<?php
/**
 * Beacons from assets/visit.js (navigator.sendBeacon, JSON as text/plain). The answer is always an empty 204, the
 * browser doesn't wait for it; what is valid gets written by Stats::collect(), everything else is dropped.
 */
declare(strict_types=1);

header('Cache-Control: no-store');
header('X-Robots-Tag: noindex');
if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    http_response_code(405);
    exit;
}
try {
    require_once dirname(__DIR__) . '/lib/stats.php';
    Stats::collect();
} catch (Throwable $e) {
    // counting must never show anything to the visitor
}
http_response_code(204);
