<?php
// The version of the latest NeoAPRS release, for version.php and download.php: neoaprs_latest_version()
// asks the GitHub releases of the project and keeps the answer in log/latest.json for ten minutes, so a
// new release needs nothing done here; while GitHub does not answer, the last good answer is returned,
// and '' when there never was one.

const MAX_AGE_SEC  = 600;     // how long the latest version is believed: a release is noticed within ten minutes (GitHub is asked at most six times an hour)
const RETRY_SEC    = 300;     // how soon GitHub is asked again after it did not answer
const VERSION_RE   = '/^\d+(\.\d+){0,3}([-+][0-9A-Za-z.]+)?$/';

// The body of a page, or null: curl where the host has it, else the stream wrapper.
function neoaprs_get(string $url): ?string
{
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
}

// The version of the latest release: the cached one while it is fresh, else
// GitHub's, else the cached one however old.
function neoaprs_latest_version(): string
{
    $releases = getenv('RELEASES_URL') ?: 'https://api.github.com/repos/oh2gba/neoaprs/releases/latest';
    $cache    = __DIR__ . '/log/latest.json';
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
    $release = json_decode((string)neoaprs_get($releases), true);
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
}
