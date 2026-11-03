<?php
/* One page view of neo.oh2gba.eu. The page reports itself once it has rendered, which counts pages that loaded rather than requests that arrived. Nothing reads the reply, so a recorded view answers 204 and sends no body.
 *
 * Counting happens in the status application's library, on the same hosting account and the same $HOME, so this site writes into the one page_views table with site = 'neo'. No cookie is set; no address or
 * user-agent is stored. See oh2gba/VISITORS.md. */
declare(strict_types=1);

ini_set('display_errors', '0');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') { http_response_code(405); exit; }
$raw = file_get_contents('php://input') ?: '';
if (strlen($raw) > 2048) { http_response_code(413); exit; }
$in = json_decode($raw, true);
if (!is_array($in)) { http_response_code(400); exit; }

/* The status application deploys the library; this site only calls it. A missing library counts nothing and still answers 204: a deploy of one site must never take a page down on another. */
$lib = getenv('STATUS_LIB') ?: (getenv('HOME') ?: '/usr/home/ohjgba') . '/public_html/status/private/lib';
if (!is_readable("$lib/visitors.php")) {
    error_log('view: no counting library at ' . $lib);
    http_response_code(204);
    exit;
}
try {
    require_once "$lib/visitors.php";
    $ip = $_SERVER['REMOTE_ADDR'] ?? '';
    $ua = $_SERVER['HTTP_USER_AGENT'] ?? '';
    if (array_key_exists('dwell', $in)) {
        visitor_dwell(status_db(), 'neo', $in, $ip, $ua);
    } else {
        visitor_record(status_db(), 'neo', $in, $ip, $ua);
    }
    http_response_code(204);
} catch (Throwable $e) {
    error_log('view: ' . $e->getMessage());
    http_response_code(500);
}
