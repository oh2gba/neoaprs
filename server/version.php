<?php
// Version check for NeoAPRS. The daemon calls this once a day with
//   version.php?v=<its version>&os=<platform>
// and gets back the latest released version, the address of the project page
// and an optional short message, as JSON. The latest version is read from the
// GitHub releases of the project and kept in log/latest.json for ten minutes, so
// a new release needs nothing done here; while GitHub does not answer, the last
// good answer is served (latest.php, which download.php uses too). message.txt
// beside this file, when it exists, is the message (its first line, 200
// characters at most).
//
// Each call is appended to a monthly log file in log/ (not web-readable, see
// log/.htaccess) as time, version and platform only, and handed to the status
// application the same way. No IP address or anything else about the caller is
// kept.

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

const PROJECT_URL  = 'https://oh2gba.github.io/neoaprs/';

require __DIR__ . '/latest.php';

$clean = static function (string $value, int $max): string {
    return substr(preg_replace('/[^0-9A-Za-z._ -]/', '', $value), 0, $max);
};
$version = $clean((string)($_GET['v'] ?? ''), 20);
$os      = $clean((string)($_GET['os'] ?? ''), 40);

$line = gmdate('Y-m-d\TH:i') . "Z\t" . ($version ?: '-') . "\t" . ($os ?: '-') . "\n";
@file_put_contents(__DIR__ . '/log/starts-' . gmdate('Y-m') . '.log', $line, FILE_APPEND | LOCK_EX);

// The same three values also go to the status application on this account,
// which shows them on status.oh2gba.eu. Its library connects with its own
// credentials; a missing or failing library must never change the answer.
$lib = getenv('STATUS_LIB') ?: (getenv('HOME') ?: '/usr/home/ohjgba') . '/public_html/status/private/lib';
if (is_readable("$lib/starts.php")) {
    try {
        require_once "$lib/starts.php";
        // the address goes in only to be hashed with the platform into a
        // per-installation key on the status side; it is not stored anywhere
        app_start_record(status_db(), 'neoaprs', $version, $os, $_SERVER['REMOTE_ADDR'] ?? '');
    } catch (Throwable $e) {
        // nothing: the file log above already has the line
    }
}

$message = '';
if (is_readable(__DIR__ . '/message.txt')) {
    $message = substr(trim(strtok((string)file_get_contents(__DIR__ . '/message.txt'), "\n") ?: ''), 0, 200);
}

echo json_encode([
    'version' => neoaprs_latest_version() ?: '0.0.0',
    'url'     => PROJECT_URL,
    'message' => $message,
], JSON_UNESCAPED_SLASHES), "\n";
