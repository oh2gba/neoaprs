<?php
/* The satellites of the map's satellites layer, served at neo.oh2gba.eu/api/v1/satellites.php: the
 * project's list of the ISS and the satellites with an APRS digipeater, each with its orbital
 * elements. An installation asks at most once a day, while its layer is on.
 *
 * The answer to a GET is the file private/satellites/satellites.json:
 *   {"v": 1, "made": TIME, "elements_at": TIME | null, "satellites": [{"id": NORAD, "name", "downlink":
 *    [{"mhz", "sure"}], "uplink": [...], "mode": {"value", "sure"}, "path": {"value", "sure"},
 *    "elements": {OMM field: text} | null}]}
 * The list is private/satellites-list.json of the repository (uploaded by server/deploy.sh --site);
 * the elements are CelesTrak's group "amateur" as CSV (OMM fields, which hold catalogue numbers above
 * 99999). Before any file exists the answer is 503 {"ok": false, "reason": "none"}; another method 405.
 *
 * CelesTrak's rules (celestrak.org/usage-policy.php, gp-data-formats.php): one download per update,
 * new data at most every 2 hours, compressed, and no further asking after an answer that is not 200.
 * So: the elements are downloaded when the served file is older than 24 hours, by one request at a
 * time (the file `lock`), never twice within 2 hours, and after a failed download (any status but
 * 200, no answer, or a body that is not the whole CSV: its header, every line a row, at least
 * MIN_ROWS rows, and no more than one of the listed satellites lost since the last download) not
 * again for 2 hours, then 6, then 24 (the file `failed` holds how many in a row); the old file is
 * served meanwhile. A changed list is merged with the last download (elements.csv) at once,
 * without asking CelesTrak. CELESTRAK_URL in the environment replaces the address (the tests). */
declare(strict_types=1);

ini_set('display_errors', '0');
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');

const SITE_ROOT     = __DIR__ . '/../..';  // neo/ on the host: this file is neo/api/v1/satellites.php
const LIST_FILE     = SITE_ROOT . '/private/satellites-list.json';
const STORE         = SITE_ROOT . '/private/satellites';
const SERVED        = STORE . '/satellites.json';
const RAW           = STORE . '/elements.csv';
const CELESTRAK     = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=amateur&FORMAT=csv';
const MAX_AGE_SEC   = 86400;
const PAUSES_SEC    = [7200, 21600, 86400];  // the wait after one, two, three or more failures in a row; the first is CelesTrak's update interval
const MIN_ROWS      = 20;
const MAX_RAW       = 4 * 1024 * 1024;
const FIELD_FORM    = '/\A[0-9A-Za-z_ .:+\-()\/]{0,40}\z/';
const MODES         = ['', 'afsk1200', 'gmsk9600'];
const PATH_FORM     = '/\A([A-Z0-9]{1,6}(-[0-9]{1,2})?(,[A-Z0-9]{1,6}(-[0-9]{1,2})?){0,7})?\z/';

function sats_answer(int $status, string $body): never
{
    http_response_code($status);
    echo $body;
    exit;
}

function sats_store(): ?string
{
    if (!is_dir(STORE) && !@mkdir(STORE, 0700, true) && !is_dir(STORE)) return null;
    if (!is_file(STORE . '/.htaccess')) @file_put_contents(STORE . '/.htaccess', "Require all denied\n");
    return STORE;
}

/** The elements' CSV, or null: one request, compressed, no redirect followed; curl where the host has it, else the stream wrapper (as latest.php asks GitHub). */
function sats_download(string $url): ?string
{
    if (function_exists('curl_init')) {
        $c = curl_init($url);
        curl_setopt_array($c, [
            CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 20, CURLOPT_CONNECTTIMEOUT => 5,
            CURLOPT_FOLLOWLOCATION => false, CURLOPT_ENCODING => 'gzip', CURLOPT_MAXFILESIZE => MAX_RAW,
            CURLOPT_HTTPHEADER => ['User-Agent: neoaprs-satellites'],
        ]);
        $body = curl_exec($c);
        $ok = is_string($body) && curl_getinfo($c, CURLINFO_RESPONSE_CODE) === 200;
        curl_close($c);
        return $ok && str_starts_with($body, 'OBJECT_NAME,') ? $body : null;
    }
    $context = stream_context_create(['http' => [
        'timeout' => 20, 'ignore_errors' => true, 'follow_location' => 0,
        'header' => "Accept-Encoding: gzip\r\nUser-Agent: neoaprs-satellites\r\n",
    ]]);
    $body = @file_get_contents($url, false, $context, 0, MAX_RAW);
    $head = $http_response_header ?? [];
    if ($body === false || $head === [] || !preg_match('#\AHTTP/\S+ 200 #', $head[0])) return null;
    foreach ($head as $line) {
        if (preg_match('/\AContent-Encoding:\s*gzip\s*\z/i', $line)) {
            $body = @gzdecode($body, MAX_RAW);
            break;
        }
    }
    return is_string($body) && str_starts_with($body, 'OBJECT_NAME,') ? $body : null;
}

/** The CSV's rows by catalogue number, only fields of the plain form; $bad counts the lines that are no row with a catalogue number. */
function sats_rows(string $csv, int &$bad = 0): array
{
    $lines = preg_split('/\r?\n/', trim($csv));
    $names = str_getcsv((string) array_shift($lines), ',', '"', '');
    $rows = [];
    $bad = 0;
    foreach ($lines as $line) {
        $values = str_getcsv($line, ',', '"', '');
        $row = count($values) === count($names) ? array_combine($names, $values) : [];
        if (!ctype_digit($row['NORAD_CAT_ID'] ?? '')) {
            $bad++;
            continue;
        }
        $ok = array_filter($row, static fn ($v, $k) => preg_match(FIELD_FORM, (string) $k) && preg_match(FIELD_FORM, (string) $v), ARRAY_FILTER_USE_BOTH);
        if (count($ok) === count($row)) $rows[(int) $row['NORAD_CAT_ID']] = $row;
    }
    return $rows;
}

/** Whether a download is the whole CSV and has not lost more than one listed satellite of the last one. */
function sats_whole(string $csv, array $list, string $last): bool
{
    $bad = 0;
    $rows = sats_rows($csv, $bad);
    if ($bad > 0 || count($rows) < MIN_ROWS) return false;
    $before = $last === '' ? [] : sats_rows($last);
    $lost = 0;
    foreach (is_array($list['satellites'] ?? null) ? $list['satellites'] : [] as $one) {
        $id = $one['id'] ?? null;
        if (is_int($id) && isset($before[$id]) && !isset($rows[$id])) $lost++;
    }
    return $lost <= 1;
}

function sats_freqs(mixed $list): array
{
    $out = [];
    foreach (is_array($list) ? $list : [] as $one) {
        $mhz = $one['mhz'] ?? null;
        if ((is_float($mhz) || is_int($mhz)) && $mhz > 1 && $mhz < 12000) $out[] = ['mhz' => (float) $mhz, 'sure' => ($one['sure'] ?? false) === true];
    }
    return $out;
}

function sats_value(mixed $item, callable $fits): array
{
    $value = is_array($item) && is_string($item['value'] ?? null) ? $item['value'] : '';
    return $fits($value) ? ['value' => $value, 'sure' => $value !== '' && ($item['sure'] ?? false) === true] : ['value' => '', 'sure' => false];
}

/** The served file: the list, each satellite with its elements or null. */
function sats_merge(array $list, array $rows, ?int $elementsAt): string
{
    $satellites = [];
    foreach (is_array($list['satellites'] ?? null) ? $list['satellites'] : [] as $one) {
        $id = $one['id'] ?? null;
        $name = $one['name'] ?? null;
        if (!is_int($id) || !is_string($name) || !preg_match('/\A[0-9A-Za-z .()\-]{1,24}\z/', $name)) continue;
        $satellites[] = [
            'id' => $id,
            'name' => $name,
            'downlink' => sats_freqs($one['downlink'] ?? []),
            'uplink' => sats_freqs($one['uplink'] ?? []),
            'mode' => sats_value($one['mode'] ?? null, static fn ($v) => in_array($v, MODES, true)),
            'path' => sats_value($one['path'] ?? null, static fn ($v) => (bool) preg_match(PATH_FORM, $v)),
            'elements' => $rows[$id] ?? null,
        ];
    }
    return json_encode([
        'v' => 1,
        'made' => gmdate('Y-m-d\TH:i:s\Z'),
        'elements_at' => $elementsAt === null ? null : gmdate('Y-m-d\TH:i:s\Z', $elementsAt),
        'satellites' => $satellites,
    ], JSON_UNESCAPED_SLASHES | JSON_PRESERVE_ZERO_FRACTION) . "\n";
}

function sats_write(string $path, string $body): bool
{
    $part = "$path.part";
    return @file_put_contents($part, $body) !== false && @rename($part, $path);
}

/** Make the served file again when it is due: a download when the elements are old, a merge when the list changed. */
function sats_refresh(): void
{
    $list = json_decode((string) @file_get_contents(LIST_FILE), true);
    if (!is_array($list) || sats_store() === null) return;
    $lock = @fopen(STORE . '/lock', 'c');
    if ($lock === false || !flock($lock, LOCK_EX | LOCK_NB)) return;   // another request is at it
    clearstatcache();
    $now = time();
    $served = is_file(SERVED) ? (int) filemtime(SERVED) : 0;
    $raw = is_file(RAW) ? (int) filemtime(RAW) : 0;
    $failed = is_file(STORE . '/failed') ? (int) filemtime(STORE . '/failed') : 0;
    $failures = $failed > 0 ? max(1, (int) @file_get_contents(STORE . '/failed')) : 0;
    $pause = PAUSES_SEC[min(max($failures, 1), count(PAUSES_SEC)) - 1];
    if ($now - $raw >= MAX_AGE_SEC && $now - $failed >= $pause) {
        $csv = sats_download(getenv('CELESTRAK_URL') ?: CELESTRAK);
        $last = $raw > 0 ? (string) @file_get_contents(RAW) : '';
        if ($csv !== null && sats_whole($csv, $list, $last) && sats_write(RAW, $csv)) {
            $raw = $now;
            $served = 0;
            @unlink(STORE . '/failed');
        } else {
            @file_put_contents(STORE . '/failed', (string) ($failures + 1));
        }
    }
    if ($served === 0 || $served < (int) filemtime(LIST_FILE) || $served < $raw) {
        $rows = $raw > 0 ? sats_rows((string) @file_get_contents(RAW)) : [];
        sats_write(SERVED, sats_merge($list, $rows, $raw > 0 ? $raw : null));
    }
    flock($lock, LOCK_UN);
    fclose($lock);
}

$method = $_SERVER['REQUEST_METHOD'] ?? '';
if ($method !== 'GET' && $method !== 'HEAD') {
    header('Allow: GET');
    sats_answer(405, json_encode(['ok' => false, 'reason' => 'method']) . "\n");
}
sats_refresh();
$body = @file_get_contents(SERVED);
if ($body === false) sats_answer(503, json_encode(['ok' => false, 'reason' => 'none']) . "\n");
sats_answer(200, $body);
