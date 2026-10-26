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
// log/.htaccess) as time, version, platform and id, tab-separated: the id is the
// random number the installation made once for itself (32 lowercase hex
// characters; anything else is ignored and logged as -), so that installations
// can be counted. The call is handed to the status application as version and
// platform. No IP address or anything else about the caller is kept.

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

const PROJECT_URL  = 'https://oh2gba.github.io/neoaprs/';

require __DIR__ . '/latest.php';

$clean = static function (string $value, int $max): string {
    return substr(preg_replace('/[^0-9A-Za-z._ -]/', '', $value), 0, $max);
};
$version = $clean((string)($_GET['v'] ?? ''), 20);
$os      = $clean((string)($_GET['os'] ?? ''), 40);

$id      = $_GET['id'] ?? '';
if (!is_string($id) || !preg_match('/\A[0-9a-f]{32}\z/', $id)) {
    $id = '';
}

$line = gmdate('Y-m-d\TH:i') . "Z\t" . ($version ?: '-') . "\t" . ($os ?: '-') . "\t" . ($id ?: '-') . "\n";
@file_put_contents(__DIR__ . '/log/starts-' . gmdate('Y-m') . '.log', $line, FILE_APPEND | LOCK_EX);

// The version, the platform and the number also go to the status application on this account,
// which shows them on status.oh2gba.eu. Its library connects with its own
// credentials; a missing or failing library must never change the answer.
$lib = getenv('STATUS_LIB') ?: (getenv('HOME') ?: '/usr/home/ohjgba') . '/public_html/status/private/lib';
if (is_readable("$lib/starts.php")) {
    try {
        require_once "$lib/starts.php";
        // the installation's random number is the per-installation key on the
        // status side; the caller's address is not used at all
        app_start_record(status_db(), 'neoaprs', $version, $os, $id);
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
