<?php
/* What the endpoints of neo.oh2gba.eu that keep a list share (api/v1/skeds.php, the sked board, and
 * api/v1/chat.php, the chat of the HF tests tab): the JSON answer and refusal, the request's body,
 * the private folder, the log, the rate limit by a salted hash of the address, the one lock, the
 * token's hash, the form of a call and the block list, a line of text, and a served file written
 * whole. It lives in private/, which Apache never serves; an endpoint requires it. */
declare(strict_types=1);

const SITE_ROOT     = __DIR__ . '/..';  // neo/ on the host: this file is neo/private/endpoint.php
const LOG_MAX_BYTES = 256 * 1024;       // each application logs under its own private/logs/, each file at most 256 KB
const CALL_FORM     = '/\A(?=[A-Z0-9]*[0-9])(?=[A-Z0-9]*[A-Z])[A-Z0-9]{3,6}(-([0-9]|1[0-5]))?\z/';  // as neoaprs/callsign.py checks our own call: an amateur call with its SSID
const PLACEHOLDERS  = ['N0CALL', 'NOCALL', 'MYCALL'];
const TOKEN_FORM    = '/\A[0-9a-f]{32}\z/';
const BLOCKED       = SITE_ROOT . '/private/skeds/blocked.txt';  // the board's block list, which the chat shares
// The white space of Unicode, made one plain space in a line of text.
const SPACES        = '/[\x{0009}-\x{000D}\x{0020}\x{0085}\x{00A0}\x{1680}\x{2000}-\x{200A}\x{2028}\x{2029}\x{202F}\x{205F}\x{3000}]+/u';

/** Answers the JSON and ends. */
function neo_answer(int $status, array $body, array $headers = []): never
{
    http_response_code($status);
    foreach ($headers as $line) header($line);
    echo json_encode($body, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_HEX_TAG | JSON_HEX_AMP | JSON_INVALID_UTF8_SUBSTITUTE), "\n";
    exit;
}

function neo_refuse(int $status, string $reason, array $headers = []): never
{
    neo_answer($status, ['ok' => false, 'reason' => $reason], $headers);
}

/** The JSON headers every answer of an endpoint carries. */
function neo_headers(): void
{
    ini_set('display_errors', '0');
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    header('X-Content-Type-Options: nosniff');
}

/**
 * The request's JSON object: a POST of application/json of at most `max` bytes, refused from its
 * Content-Length before anything is read.
 */
function neo_request(int $max): array
{
    if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') neo_refuse(405, 'method', ['Allow: POST']);
    if ((int) ($_SERVER['CONTENT_LENGTH'] ?? 0) > $max) neo_refuse(413, 'too_large');
    $type = strtolower(trim(explode(';', (string) ($_SERVER['CONTENT_TYPE'] ?? ''))[0]));
    if ($type !== 'application/json') neo_refuse(415, 'bad_request');
    $raw = (string) @file_get_contents('php://input', false, null, 0, $max + 1);
    if (strlen($raw) > $max) neo_refuse(413, 'too_large');
    $in = json_decode($raw, true, 4);
    if (!is_array($in) || array_is_list($in)) neo_refuse(400, 'bad_request');
    return $in;
}

/**
 * A folder under private/ with its own .htaccess (private/ is refused by its own and the site's
 * rule already).
 */
function neo_folder(string $dir): string
{
    if (!is_dir($dir) && !@mkdir($dir, 0700, true) && !is_dir($dir)) neo_refuse(500, 'storage');
    if (!is_file("$dir/.htaccess")) @file_put_contents("$dir/.htaccess", "Require all denied\n");
    return $dir;
}

/**
 * A line in private/logs/NAME.log; the older half goes past 256 KB. No address, token or text is
 * written.
 */
function neo_log(string $name, string $line): void
{
    $folder = SITE_ROOT . '/private/logs';
    if (!is_dir($folder) && !@mkdir($folder, 0700, true) && !is_dir($folder)) return;
    $path = "$folder/$name.log";
    if (is_file($path) && filesize($path) > LOG_MAX_BYTES) @file_put_contents($path, substr((string) file_get_contents($path), (int) (LOG_MAX_BYTES / 2)), LOCK_EX);
    @file_put_contents($path, gmdate('Y-m-d\TH:i:s\Z') . "  $line\n", FILE_APPEND | LOCK_EX);
}

/**
 * The address as it is hashed: an IPv6 address by its first 64 bits (the rest is the household's to
 * choose).
 */
function neo_address(): string
{
    $ip = (string) ($_SERVER['REMOTE_ADDR'] ?? '');
    $raw = @inet_pton($ip);
    if ($raw === false) return $ip;
    return strlen($raw) === 16 ? substr($raw, 0, 8) : $raw;
}

/**
 * Count this request against the address and the whole in `file` of the folder; false when either
 * has used its share of the last `window` seconds. Only hashes under the folder's own salt are kept.
 */
function neo_allowed(string $dir, string $address, int $now, string $file, int $per, int $inAll, int $window): bool
{
    $saltFile = "$dir/salt";
    if (!is_file($saltFile)) @file_put_contents($saltFile, bin2hex(random_bytes(16)), LOCK_EX);
    $key = substr(hash('sha256', trim((string) @file_get_contents($saltFile)) . '|' . $address), 0, 16);
    $h = @fopen("$dir/$file", 'c+');
    if ($h === false) neo_refuse(500, 'storage');
    flock($h, LOCK_EX);
    $seen = json_decode((string) stream_get_contents($h), true);
    $seen = is_array($seen) ? $seen : [];
    $kept = [];
    $all = 0;
    foreach ($seen as $k => $times) {
        if (!is_array($times)) continue;
        $times = array_values(array_filter($times, fn($t) => is_int($t) && $t > $now - $window));
        if ($times) { $kept[$k] = $times; $all += count($times); }
    }
    $mine = count($kept[$key] ?? []);
    $ok = $mine < $per && $all < $inAll;
    if ($ok) $kept[$key][] = $now;
    ftruncate($h, 0);
    rewind($h);
    fwrite($h, json_encode($kept));
    flock($h, LOCK_UN);
    fclose($h);
    return $ok;
}

/**
 * The one lock every change of the folder and its served files is made under; released when the
 * request ends.
 */
function neo_lock(string $dir): mixed
{
    $h = @fopen("$dir/lock", 'c');
    if ($h === false || !flock($h, LOCK_EX)) neo_refuse(500, 'storage');
    return $h;
}

/** The hash of a token (32 lowercase hex digits) as it is kept, else null. */
function neo_token_hash(mixed $value): ?string
{
    return is_string($value) && preg_match(TOKEN_FORM, $value) ? hash('sha256', $value) : null;
}

function neo_iso(int $at): string
{
    return gmdate('Y-m-d\TH:i:s\Z', $at);
}

/** The call in its normal form (upper case, no SSID of 0) when it is an amateur call, else null. */
function neo_call(mixed $value): ?string
{
    if (!is_string($value)) return null;
    $call = strtoupper(trim($value));
    if (!preg_match(CALL_FORM, $call)) return null;
    if (str_ends_with($call, '-0')) $call = substr($call, 0, -2);
    return in_array(neo_base($call), PLACEHOLDERS, true) ? null : $call;
}

/** The call without its SSID: a blocked call is blocked with every SSID. */
function neo_base(string $call): string
{
    return explode('-', $call)[0];
}

/** The blocked calls (the board's blocked.txt, one on each line). */
function neo_blocked(): array
{
    $lines = @file(BLOCKED, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    return $lines === false ? [] : array_values(array_filter(array_map(fn($l) => strtoupper(trim((string) $l)), $lines), fn($l) => $l !== '' && $l[0] !== '#'));
}

function neo_is_blocked(string $call, array $blocked): bool
{
    return in_array($call, $blocked, true) || in_array(neo_base($call), $blocked, true);
}

/**
 * One line of text: the white space of Unicode becomes one space, every character outside `kept` (a
 * character class) is removed, runs of spaces become one, cut to `max` characters. Null when not
 * UTF-8 text.
 */
function neo_line(mixed $value, int $max, string $kept): ?string
{
    if (!is_string($value) || !preg_match('//u', $value)) return null;
    $spaced = (string) preg_replace(SPACES, ' ', $value);
    $left = (string) preg_replace('/[^' . $kept . ']/u', '', $spaced);
    $left = trim((string) preg_replace('/ {2,}/', ' ', $left));
    $chars = preg_split('//u', $left, $max + 1, PREG_SPLIT_NO_EMPTY);
    return trim(implode('', array_slice($chars === false ? [] : $chars, 0, $max)));
}

/** Writes a served file whole (a .part, then renamed), so a reader never gets half of it. */
function neo_publish(string $path, array $value): void
{
    $json = json_encode($value, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_HEX_TAG | JSON_HEX_AMP);
    $part = $path . '.part';
    if ($json === false || @file_put_contents($part, $json . "\n") === false || !@rename($part, $path)) {
        @unlink($part);
        neo_refuse(500, 'storage');
    }
}
