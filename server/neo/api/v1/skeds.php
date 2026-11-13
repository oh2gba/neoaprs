<?php
/* The sked board of NeoAPRS, served at neo.oh2gba.eu/api/v1/skeds.php: when someone will be on the air, and on which dial. The Skeds tab of the program posts here, only when the operator presses Post or Delete.
 *
 * Reading is not done here: every accepted change writes the board to skeds.json in the root of the site (BOARD below, beside frequencies.json), which Apache serves as a static file and the program, its page and
 * the project page read. The board is {"v": 1, "written": TIME, "closed": false, "skeds": [{"id", "call", "from", "to", "dial", "note"}, ...]}, sorted by `from`, at most 100 rows, never a token or its hash.
 *
 * Writing is a POST of application/json, at most 2048 bytes, refused from its Content-Length before anything is read:
 *
 *   {"action": "add", "token": "<32 hex>", "call": "OH2GBA", "from": "2026-11-14T18:00:00Z", "to": "2026-11-14T20:00:00Z", "dial": "7.0541 MHz USB", "note": "Mercury, 10 W"}   -> {"ok": true, "id": ID, "board": BOARD}
 *   {"action": "remove", "token": "<32 hex>", "id": "<12 hex>"}                                                                                                                 -> {"ok": true, "board": BOARD}
 *   {"action": "refresh"}                                                                                                                                                       -> {"ok": true, "board": BOARD}
 *
 * A refusal is {"ok": false, "reason": CODE} with a status that says it too: 405 method, 413 too_large, 415 bad_request (not application/json), 400 bad_request, 429 rate, 403 closed (the board is closed, or
 * the call is blocked), 403 not_yours, 409 full, 422 past, too_long or too_far, 500 storage.
 *
 * What is refused: a `to` not after the server's now (past), a `from` more than 30 days ahead (too_far), a sked longer than 24 hours (too_long), a sixth sked to come for one token, an eleventh under one call (any SSID of it)
 * or a hundred and first in all (full). Only the server's clock decides. The call has the form of an amateur call (3 to 6 letters and digits with a digit and a letter, an SSID of 0 to 15), the dial the form the
 * program shows ("7.0541 MHz USB"), the note one line of 80 characters at most with control and invisible characters removed. The same sked posted again under the same token is answered with its id.
 *
 * Who may delete: each installation of the program makes a random token once; the hash of the token is kept with the sked (never on the board), so only the installation that posted a sked can remove it. An id
 * that is not on the board any more (it has ended) is answered with the board.
 *
 * What is kept: one file per sked, ID.json, in private/skeds/ of this site (Apache refuses to serve private/), written to a .part and renamed, under one lock (the file `lock`); ended skeds, and the skeds of a
 * blocked call, are removed at every write. The sender's address is never written down: it is hashed under a salt that only this folder knows, for the rate limit (10 adds an hour from one address, 60 an hour
 * in all; an add is counted once it is well formed and within the times, and so is a remove with a wrong token or of an id that is gone; a remove with the right token is not, nor a refresh, so that a flood
 * cannot keep the moderator from making the board again), and the hash is forgotten after the hour. A refresh writes the board only when what it says has changed.
 *
 * The moderation (server/skeds.sh, over SFTP): a file `closed` in the folder makes every add answer `closed` and the board say "closed": true; `blocked.txt` holds a call on each line whose adds answer `closed`
 * and whose skeds are removed. Removing a file there and posting a refresh makes the board again. */
declare(strict_types=1);

ini_set('display_errors', '0');
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');

const SITE_ROOT        = __DIR__ . '/../..';                     // neo/ on the host: this file is neo/api/v1/skeds.php
const BOARD            = SITE_ROOT . '/skeds.json';
const STORE            = SITE_ROOT . '/private/skeds';
const MAX_BODY         = 2048;
const MAX_NOTE         = 80;
const MAX_AHEAD_SEC    = 30 * 86400;
const MAX_LENGTH_SEC   = 24 * 3600;
const MAX_PER_TOKEN    = 5;
const MAX_PER_CALL     = 10;
const MAX_IN_ALL       = 100;
const RATE_PER_ADDRESS = 10;
const RATE_IN_ALL      = 60;
const RATE_WINDOW_SEC  = 3600;
const LOG_MAX_BYTES    = 256 * 1024;                              // of the log (oh2gba/SHARED-HOST.md: each application logs under its own private/logs/, each file capped at 256 KB)
const TIME_FORM        = '/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/';
const DIAL_FORM        = '/^\d{1,2}\.\d{3,4} MHz (USB|LSB)$/';    // as neoaprs/versions.py reads a dial and the HF box shows it
const CALL_FORM        = '/^(?=[A-Z0-9]*[0-9])(?=[A-Z0-9]*[A-Z])[A-Z0-9]{3,6}(-([0-9]|1[0-5]))?$/';      // as neoaprs/callsign.py checks our own call: an amateur call with its SSID
const PLACEHOLDERS     = ['N0CALL', 'NOCALL', 'MYCALL'];
const ID_FORM          = '/^[0-9a-f]{12}$/';
const TOKEN_FORM       = '/^[0-9a-f]{32}$/';

/** Answers the JSON and ends. */
function skeds_answer(int $status, array $body, array $headers = []): never
{
    http_response_code($status);
    foreach ($headers as $line) header($line);
    echo json_encode($body, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_HEX_TAG | JSON_HEX_AMP | JSON_INVALID_UTF8_SUBSTITUTE), "\n";
    exit;
}

function skeds_refuse(int $status, string $reason, array $headers = []): never
{
    skeds_answer($status, ['ok' => false, 'reason' => $reason], $headers);
}

/** The folder of the stored skeds, with one more .htaccess of its own (private/ is refused already by its own and by the rule of the site's .htaccess). */
function skeds_store(): string
{
    $dir = STORE;
    if (!is_dir($dir) && !@mkdir($dir, 0700, true) && !is_dir($dir)) skeds_refuse(500, 'storage');
    if (!is_file("$dir/.htaccess")) @file_put_contents("$dir/.htaccess", "Require all denied\n");
    return $dir;
}

/** A line in private/logs/skeds.log; the older half goes when it has grown past 256 KB. No address, no token and no note are written to it. */
function skeds_log(string $line): void
{
    $folder = SITE_ROOT . '/private/logs';
    if (!is_dir($folder) && !@mkdir($folder, 0700, true) && !is_dir($folder)) return;
    $path = "$folder/skeds.log";
    if (is_file($path) && filesize($path) > LOG_MAX_BYTES) @file_put_contents($path, substr((string) file_get_contents($path), (int) (LOG_MAX_BYTES / 2)), LOCK_EX);
    @file_put_contents($path, gmdate('Y-m-d\TH:i:s\Z') . "  $line\n", FILE_APPEND | LOCK_EX);
}

/** The address as it is hashed: an IPv6 address by its first 64 bits (the rest is the household's to choose). */
function skeds_address(): string
{
    $ip = (string) ($_SERVER['REMOTE_ADDR'] ?? '');
    $raw = @inet_pton($ip);
    if ($raw === false) return $ip;
    return strlen($raw) === 16 ? substr($raw, 0, 8) : $raw;
}

/** Counts this request against the address and the whole; false when either has used its share of the last hour. Only hashes are kept, and only for the hour. */
function skeds_allowed(string $dir, string $address, int $now): bool
{
    $saltFile = "$dir/salt";
    if (!is_file($saltFile)) @file_put_contents($saltFile, bin2hex(random_bytes(16)), LOCK_EX);
    $key = substr(hash('sha256', trim((string) @file_get_contents($saltFile)) . '|' . $address), 0, 16);
    $h = @fopen("$dir/rate.json", 'c+');
    if ($h === false) skeds_refuse(500, 'storage');
    flock($h, LOCK_EX);
    $seen = json_decode((string) stream_get_contents($h), true);
    $seen = is_array($seen) ? $seen : [];
    $kept = [];
    $all = 0;
    foreach ($seen as $k => $times) {
        if (!is_array($times)) continue;
        $times = array_values(array_filter($times, fn($t) => is_int($t) && $t > $now - RATE_WINDOW_SEC));
        if ($times) { $kept[$k] = $times; $all += count($times); }
    }
    $mine = count($kept[$key] ?? []);
    $ok = $mine < RATE_PER_ADDRESS && $all < RATE_IN_ALL;
    if ($ok) $kept[$key][] = $now;
    ftruncate($h, 0);
    rewind($h);
    fwrite($h, json_encode($kept));
    flock($h, LOCK_UN);
    fclose($h);
    return $ok;
}

/** The one lock every change of the folder and the board is made under; released when the request ends. */
function skeds_lock(string $dir): mixed
{
    $h = @fopen("$dir/lock", 'c');
    if ($h === false || !flock($h, LOCK_EX)) skeds_refuse(500, 'storage');
    return $h;
}

/**
 * The id of a sked when the value is one (12 lowercase hex digits), else null. What comes out is only those digits, so it can name a file of the folder and nothing outside it: Psalm is told so here, since it
 * cannot follow a pattern.
 *
 * @psalm-taint-escape file
 */
function skeds_id(mixed $value): ?string
{
    return is_string($value) && preg_match(ID_FORM, $value) ? $value : null;
}

/** The hash of a token (32 lowercase hex digits) as it is kept with a sked, else null. */
function skeds_token_hash(mixed $value): ?string
{
    return is_string($value) && preg_match(TOKEN_FORM, $value) ? hash('sha256', $value) : null;
}

/** The instant of a time of the form 2026-11-14T18:00:00Z, else null (a day or an hour that does not exist is no time). */
function skeds_time(mixed $value): ?int
{
    if (!is_string($value) || !preg_match(TIME_FORM, $value)) return null;
    $at = DateTimeImmutable::createFromFormat('!Y-m-d\TH:i:s\Z', $value, new DateTimeZone('UTC'));
    return $at !== false && $at->format('Y-m-d\TH:i:s\Z') === $value ? $at->getTimestamp() : null;
}

function skeds_iso(int $at): string
{
    return gmdate('Y-m-d\TH:i:s\Z', $at);
}

/** The call in its normal form (upper case, no SSID of 0) when it is an amateur call, else null. */
function skeds_call(mixed $value): ?string
{
    if (!is_string($value)) return null;
    $call = strtoupper(trim($value));
    if (!preg_match(CALL_FORM, $call)) return null;
    if (str_ends_with($call, '-0')) $call = substr($call, 0, -2);
    return in_array(skeds_base($call), PLACEHOLDERS, true) ? null : $call;
}

function skeds_dial(mixed $value): ?string
{
    if (!is_string($value)) return null;
    $dial = trim($value);
    return preg_match(DIAL_FORM, $dial) ? $dial : null;
}

/** The note: one line of letters, marks, digits, punctuation, the printable ASCII and plain spaces; every other character (a control, a format or invisible one, a symbol beyond ASCII) is removed, every run of
 * spaces and line breaks is one space, and it is cut to 80 characters. Null when it is not text in UTF-8. */
function skeds_note(mixed $value): ?string
{
    if ($value === null) return '';
    if (!is_string($value) || !preg_match('//u', $value)) return null;
    $spaced = (string) preg_replace('/[\s\x{00A0}\x{1680}\x{2000}-\x{200A}\x{2028}\x{2029}\x{202F}\x{205F}\x{3000}]+/u', ' ', $value);
    $kept = (string) preg_replace('/[^\x{0020}-\x{007E}\p{L}\p{M}\p{N}\p{P}]/u', '', $spaced);
    $kept = trim((string) preg_replace('/ {2,}/', ' ', $kept));
    $chars = preg_split('//u', $kept, MAX_NOTE + 1, PREG_SPLIT_NO_EMPTY);
    return trim(implode('', array_slice($chars === false ? [] : $chars, 0, MAX_NOTE)));
}

/** The calls whose adds are refused (blocked.txt of the folder, one on each line). */
function skeds_blocked(string $dir): array
{
    $lines = @file("$dir/blocked.txt", FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    return $lines === false ? [] : array_values(array_filter(array_map(fn($l) => strtoupper(trim((string) $l)), $lines), fn($l) => $l !== '' && $l[0] !== '#'));
}

/** The call without its SSID: the limit of skeds under one call and a blocked call hold for every SSID of it. */
function skeds_base(string $call): string
{
    return explode('-', $call)[0];
}

function skeds_is_blocked(string $call, array $blocked): bool
{
    return in_array($call, $blocked, true) || in_array(skeds_base($call), $blocked, true);
}

/** The stored skeds that are still to come, by id; an ended one, one of a blocked call and a file that is not a sked of ours are removed. Under the lock only. */
function skeds_stored(string $dir, int $now): array
{
    $blocked = skeds_blocked($dir);
    $found = [];
    foreach ((array) @scandir($dir) as $name) {
        if (!is_string($name) || !preg_match('/^([0-9a-f]{12})\.json$/', $name, $m)) continue;
        $id = $m[1];
        $row = json_decode((string) @file_get_contents("$dir/$name"), true);
        $from = is_array($row) ? skeds_time($row['from'] ?? null) : null;
        $to = is_array($row) ? skeds_time($row['to'] ?? null) : null;
        $call = is_array($row) ? skeds_call($row['call'] ?? null) : null;
        $good = $from !== null && $to !== null && $call !== null && ($row['id'] ?? null) === $id && skeds_dial($row['dial'] ?? null) !== null && is_string($row['note'] ?? '');
        if (!$good || $to <= $now || skeds_is_blocked($call, $blocked)) {
            @unlink("$dir/$name");
            continue;
        }
        $found[$id] = ['at' => $from] + $row;
    }
    uasort($found, fn($a, $b) => [$a['at'], $a['id']] <=> [$b['at'], $b['id']]);
    return $found;
}

/** The rows of the board from the stored skeds: at most a hundred, never a token. Under the lock only. */
function skeds_rows(string $dir, int $now): array
{
    $rows = [];
    foreach (array_slice(skeds_stored($dir, $now), 0, MAX_IN_ALL) as $row) {
        $rows[] = ['id' => (string) $row['id'], 'call' => (string) $row['call'], 'from' => (string) $row['from'], 'to' => (string) $row['to'], 'dial' => (string) $row['dial'], 'note' => (string) ($row['note'] ?? '')];
    }
    return $rows;
}

/** Writes the board from the stored skeds, or from `rows` when they are given (a .part, then renamed) and returns it. Under the lock only. */
function skeds_write_board(string $dir, int $now, ?array $rows = null): array
{
    $rows ??= skeds_rows($dir, $now);
    $board = ['v' => 1, 'written' => skeds_iso($now), 'closed' => is_file("$dir/closed"), 'skeds' => $rows];
    $json = json_encode($board, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_HEX_TAG | JSON_HEX_AMP);
    $part = BOARD . '.part';
    if ($json === false || @file_put_contents($part, $json . "\n") === false || !@rename($part, BOARD)) {
        @unlink($part);
        skeds_refuse(500, 'storage');
    }
    return $board;
}

/** Writes one sked's file (a .part, then renamed). */
function skeds_keep(string $dir, string $id, array $row): void
{
    $json = json_encode($row, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
    $part = "$dir/$id.json.part";
    if ($json === false || @file_put_contents($part, $json . "\n") === false || !@rename($part, "$dir/$id.json")) {
        @unlink($part);
        skeds_refuse(500, 'storage');
    }
    @chmod("$dir/$id.json", 0600);
}

function skeds_new_id(array $stored): string
{
    do {
        $id = bin2hex(random_bytes(6));
    } while (isset($stored[$id]));
    return $id;
}

function skeds_add(string $dir, array $in, int $now): never
{
    if (is_file("$dir/closed")) skeds_refuse(403, 'closed');
    $hash = skeds_token_hash($in['token'] ?? null);
    $call = skeds_call($in['call'] ?? null);
    $from = skeds_time($in['from'] ?? null);
    $to = skeds_time($in['to'] ?? null);
    $dial = skeds_dial($in['dial'] ?? null);
    $note = skeds_note($in['note'] ?? null);
    if ($hash === null || $call === null || $from === null || $to === null || $dial === null || $note === null || $to <= $from) skeds_refuse(400, 'bad_request');
    if (skeds_is_blocked($call, skeds_blocked($dir))) skeds_refuse(403, 'closed');
    if ($to <= $now) skeds_refuse(422, 'past');
    if ($to - $from > MAX_LENGTH_SEC) skeds_refuse(422, 'too_long');
    if ($from > $now + MAX_AHEAD_SEC) skeds_refuse(422, 'too_far');
    if (!skeds_allowed($dir, skeds_address(), $now)) skeds_refuse(429, 'rate', ['Retry-After: ' . RATE_WINDOW_SEC]);

    $lock = skeds_lock($dir);
    $stored = skeds_stored($dir, $now);
    $fromIso = skeds_iso($from);
    $toIso = skeds_iso($to);
    $mine = 0;
    $ofCall = 0;
    foreach ($stored as $id => $row) {
        if (($row['token'] ?? '') === $hash) {
            if ($row['call'] === $call && $row['from'] === $fromIso && $row['to'] === $toIso && $row['dial'] === $dial && ($row['note'] ?? '') === $note) {
                skeds_answer(200, ['ok' => true, 'id' => (string) $id, 'board' => skeds_write_board($dir, $now)]);
            }
            $mine++;
        }
        if (skeds_base($row['call']) === skeds_base($call)) $ofCall++;
    }
    if ($mine >= MAX_PER_TOKEN || $ofCall >= MAX_PER_CALL || count($stored) >= MAX_IN_ALL) skeds_refuse(409, 'full');
    $id = skeds_new_id($stored);
    skeds_keep($dir, $id, ['id' => $id, 'call' => $call, 'from' => $fromIso, 'to' => $toIso, 'dial' => $dial, 'note' => $note, 'token' => $hash, 'posted' => skeds_iso($now)]);
    $board = skeds_write_board($dir, $now);
    flock($lock, LOCK_UN);
    skeds_answer(200, ['ok' => true, 'id' => $id, 'board' => $board]);
}

function skeds_remove(string $dir, array $in, int $now): never
{
    $hash = skeds_token_hash($in['token'] ?? null);
    $id = skeds_id($in['id'] ?? null);
    if ($hash === null || $id === null) skeds_refuse(400, 'bad_request');
    $lock = skeds_lock($dir);
    $stored = skeds_stored($dir, $now);
    $mine = isset($stored[$id]) && hash_equals((string) ($stored[$id]['token'] ?? ''), $hash);
    if (!$mine) {
        flock($lock, LOCK_UN);                                    // (a wrong token, and an id that is not on the board any more, are counted; the right token is not)
        if (!skeds_allowed($dir, skeds_address(), $now)) skeds_refuse(429, 'rate', ['Retry-After: ' . RATE_WINDOW_SEC]);
        if (isset($stored[$id])) skeds_refuse(403, 'not_yours');
        $lock = skeds_lock($dir);
    } elseif (!@unlink("$dir/$id.json")) {
        skeds_refuse(500, 'storage');
    }
    $board = skeds_write_board($dir, $now);
    flock($lock, LOCK_UN);
    skeds_answer(200, ['ok' => true, 'board' => $board]);
}

/** The board made again from the stored skeds; the file is written only when its rows or its `closed` differ from what is served, so a refresh is not counted and costs no write when nothing changed. */
function skeds_refresh(string $dir, int $now): never
{
    $lock = skeds_lock($dir);
    $served = json_decode((string) @file_get_contents(BOARD), true);
    $rows = skeds_rows($dir, $now);
    $same = is_array($served) && ($served['v'] ?? null) === 1 && is_string($served['written'] ?? null) && ($served['closed'] ?? null) === is_file("$dir/closed") && ($served['skeds'] ?? null) === $rows;
    $board = $same ? $served : skeds_write_board($dir, $now, $rows);
    flock($lock, LOCK_UN);
    skeds_answer(200, ['ok' => true, 'board' => $board]);
}

function skeds_receive(): never
{
    if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') skeds_refuse(405, 'method', ['Allow: POST']);
    if ((int) ($_SERVER['CONTENT_LENGTH'] ?? 0) > MAX_BODY) skeds_refuse(413, 'too_large');
    $type = strtolower(trim(explode(';', (string) ($_SERVER['CONTENT_TYPE'] ?? ''))[0]));
    if ($type !== 'application/json') skeds_refuse(415, 'bad_request');
    $raw = (string) @file_get_contents('php://input', false, null, 0, MAX_BODY + 1);
    if (strlen($raw) > MAX_BODY) skeds_refuse(413, 'too_large');
    $in = json_decode($raw, true, 4);
    if (!is_array($in) || array_is_list($in)) skeds_refuse(400, 'bad_request');

    $now = time();
    $dir = skeds_store();
    $action = $in['action'] ?? null;
    if ($action === 'remove') skeds_remove($dir, $in, $now);
    if ($action === 'refresh') skeds_refresh($dir, $now);
    if ($action !== 'add') skeds_refuse(400, 'bad_request');
    skeds_add($dir, $in, $now);
}

try {
    skeds_receive();
} catch (Throwable $e) {
    skeds_log('error: ' . get_class($e) . ': ' . str_replace(["\r", "\n"], ' ', $e->getMessage()));
    skeds_refuse(500, 'storage');
}
