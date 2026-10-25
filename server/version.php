<?php
// Version check for NeoAPRS. The daemon calls this once a day with
//   version.php?v=<its version>&os=<platform>
// and gets back the latest released version, the address of the project page
// and an optional short message, as JSON. The latest version is read from the
// GitHub releases of the project and kept in log/latest.json for ten minutes, so
// a new release needs nothing done here; while GitHub does not answer, the last
// good answer is served. message.txt beside this file, when it exists, is the
// message (its first line, 200 characters at most).
//
// Each call is appended to a monthly log file in log/ (not web-readable, see
// log/.htaccess) as time, version and platform only, and handed to the status
// application the same way. No IP address or anything else about the caller is
// kept.

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

const PROJECT_URL  = 'https://oh2gba.github.io/neoaprs/';
const MAX_AGE_SEC  = 600;     // how long the latest version is believed: a release is noticed within ten minutes (GitHub is asked at most six times an hour)
const RETRY_SEC    = 300;     // how soon GitHub is asked again after it did not answer
const VERSION_RE   = '/^\d+(\.\d+){0,3}([-+][0-9A-Za-z.]+)?$/';

$releases = getenv('RELEASES_URL') ?: 'https://api.github.com/repos/oh2gba/neoaprs/releases/latest';
$cache    = __DIR__ . '/log/latest.json';

// The body of a page, or null: curl where the host has it, else the stream wrapper.
$get = static function (string $url): ?string {
    if (function_exists('curl_init')) {
        $c = curl_init($url);
        curl_setopt_array($c, [
            CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 5, CURLOPT_CONNECTTIMEOUT => 3,
            CURLOPT_HTTPHEADER => ['Accept: application/vnd.github+json', 'User-Agent: neoaprs-version-page'],
        ]);
        $body = curl_exec($c);
        $ok = $body !== false && curl_getinfo($c, CURLINFO_RESPONSE_CODE) === 200;
        curl_close($c);
        return $ok ? $body : null;
    }
    $context = stream_context_create(['http' => [
        'timeout' => 5, 'ignore_errors' => true,
        'header' => "Accept: application/vnd.github+json\r\nUser-Agent: neoaprs-version-page\r\n",
    ]]);
    $body = @file_get_contents($url, false, $context);
    return $body !== false && ($http_response_header[0] ?? '') !== '' && strpos($http_response_header[0], ' 200 ') !== false ? $body : null;
};

// The version of the latest release: the cached one while it is fresh, else
// GitHub's, else the cached one however old.
$latest = static function () use ($cache, $releases, $get): string {
    $known = json_decode((string)@file_get_contents($cache), true);
    $known = is_array($known) && preg_match(VERSION_RE, (string)($known['version'] ?? '')) ? (string)$known['version'] : '';
    $age = $known !== '' ? time() - (int)@filemtime($cache) : PHP_INT_MAX;
    if ($age <= MAX_AGE_SEC) {
        return $known;
    }
    $lock = @fopen($cache . '.lock', 'c');
    if ($lock === false || !flock($lock, LOCK_EX | LOCK_NB)) {
        return $known;                      // another call is asking GitHub
    }
    $release = json_decode((string)$get($releases), true);
    $version = is_array($release) ? ltrim((string)($release['tag_name'] ?? ''), 'vV') : '';
    if (preg_match(VERSION_RE, $version)) {
        $tmp = $cache . '.' . getmypid();
        if (@file_put_contents($tmp, json_encode(['version' => $version])) !== false) {
            @rename($tmp, $cache);
        }
        $known = $version;
    } elseif ($known !== '') {
        @touch($cache, time() - MAX_AGE_SEC + RETRY_SEC);     // the old answer stands; ask again in a few minutes
    }
    flock($lock, LOCK_UN);
    fclose($lock);
    return $known;
};

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
    'version' => $latest() ?: '0.0.0',
    'url'     => PROJECT_URL,
    'message' => $message,
], JSON_UNESCAPED_SLASHES), "\n";
