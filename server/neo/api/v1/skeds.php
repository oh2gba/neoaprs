<?php
/* The sked board of NeoAPRS, served at neo.oh2gba.eu/api/v1/skeds.php: when someone will be on the air and
 * on which dial. The program's Skeds tab posts here only when the operator presses Post or Delete.
 *
 * Reading is not done here: every accepted change writes the board to skeds.json in the site root (BOARD),
 * which Apache serves as a static file. The board is {"v": 1, "written": TIME, "closed": false,
 * "skeds": [{"id", "call", "from", "to", "dial", "note"}, ...]}, the skeds still to come sorted by `from`,
 * at most 100 rows, never a token or its hash. The same write makes skeds-past.json beside it (PAST),
 * {"v": 1, "written": TIME, "past": [ROW, ...]}: rows of the same form whose end has passed, the 20 newest
 * tests (rows with the same times and dial are one test) by their end, newest first, at most 100 rows.
 * The past tests are a file of their own so that skeds.json, and every answer to a request an older
 * reader makes, stay byte for byte what they were: only a request with "past": true has the key `past`
 * (PAST's value) added to its answer.
 *
 * Writing is a POST of application/json, at most 2048 bytes, refused from its Content-Length before
 * anything is read:
 *
 *   {"action": "add", "token": "<32 hex>", "call": "OH2GBA", "from": "2026-11-14T18:00:00Z",
 *    "to": "2026-11-14T20:00:00Z", "dial": "7.0541 MHz USB", "note": "Mercury, 10 W"}  -> {"ok": true, "id": ID, "board": BOARD}
 *   {"action": "remove", "token": "<32 hex>", "id": "<12 hex>"}  -> {"ok": true, "board": BOARD}
 *   {"action": "refresh"}                                        -> {"ok": true, "board": BOARD}
 *
 * A refusal is {"ok": false, "reason": CODE} with a matching status: 405 method, 413 too_large,
 * 415 bad_request (not application/json), 400 bad_request, 429 rate, 403 closed (board closed or call
 * blocked), 403 not_yours, 409 full, 422 past, too_long or too_far, 500 storage.
 *
 * What is refused: a `to` not after the server's now (past), a `from` more than 30 days ahead (too_far),
 * a sked longer than 24 hours (too_long), a sixth sked to come for one token, an eleventh under one call
 * (any SSID) or a hundred and first in all (full). Only the server's clock decides. The call has the form
 * of an amateur call (3 to 6 letters and digits with a digit and a letter, SSID 0 to 15), the dial the
 * form the program shows ("7.0541 MHz USB"), the note one line of at most 80 characters with control and
 * invisible characters removed. The same sked posted again under the same token is answered with its id.
 *
 * Who may delete: each installation makes a random token once; the hash of the token is kept with the
 * sked (never on the board), so only the installation that posted a sked can remove it. A sked removed
 * before it began is gone; one removed while it runs ends then and stays as a past test. An id that is no
 * longer on the board (it has ended) is answered with the board: a past test is never removed or changed
 * by a request.
 *
 * What is kept: one file per sked, ID.json, in private/skeds/ (Apache refuses to serve private/),
 * written to a .part and renamed under one lock (the file `lock`); skeds that ended more than 30 days
 * ago, the oldest past ones beyond 1000, and those of a blocked call are removed at every write. The
 * sender's address is never written down: it is hashed under a salt
 * only this folder knows, for the rate limit (10 adds an hour from one address, 60 an hour in all; an
 * add counts once it is well formed and within the times, and so does a remove with a wrong token or of
 * an id that is gone; a remove with the right token and a refresh do not, so a flood cannot keep the
 * moderator from remaking the board). The hash is forgotten after the hour. A refresh writes each file
 * only when what it says has changed.
 *
 * Moderation (server/skeds.sh, over SFTP): a file `closed` in the folder makes every add answer `closed`
 * and the board say "closed": true; `blocked.txt` holds a call per line whose adds answer `closed` and
 * whose skeds, past ones too, are removed. Removing a file there and posting a refresh makes the board
 * again. */
declare(strict_types=1);

ini_set('display_errors', '0');
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');

const SITE_ROOT        = __DIR__ . '/../..';  // neo/ on the host: this file is neo/api/v1/skeds.php
const BOARD            = SITE_ROOT . '/skeds.json';
const PAST             = SITE_ROOT . '/skeds-past.json';
const STORE            = SITE_ROOT . '/private/skeds';
const MAX_BODY         = 2048;
const MAX_NOTE         = 80;
const MAX_AHEAD_SEC    = 30 * 86400;
const MAX_LENGTH_SEC   = 24 * 3600;
const MAX_PER_TOKEN    = 5;
const MAX_PER_CALL     = 10;
const MAX_IN_ALL       = 100;
const KEEP_PAST_SEC    = 30 * 86400;
const MAX_PAST_TESTS   = 20;
const MAX_PAST_ROWS    = 100;
const MAX_PAST_KEPT    = 1000;
const RATE_PER_ADDRESS = 10;
const RATE_IN_ALL      = 60;
const RATE_WINDOW_SEC  = 3600;
const LOG_MAX_BYTES    = 256 * 1024;  // log cap: each application logs under its own private/logs/, each file at most 256 KB
const TIME_FORM        = '/\A\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\z/';
const DIAL_FORM        = '/\A\d{1,2}\.\d{3,4} MHz (USB|LSB)\z/';  // as neoaprs/versions.py reads a dial and the HF box shows it
const CALL_FORM        = '/\A(?=[A-Z0-9]*[0-9])(?=[A-Z0-9]*[A-Z])[A-Z0-9]{3,6}(-([0-9]|1[0-5]))?\z/';  // as neoaprs/callsign.py checks our own call: an amateur call with its SSID
const PLACEHOLDERS     = ['N0CALL', 'NOCALL', 'MYCALL'];
const ID_FORM          = '/\A[0-9a-f]{12}\z/';
const TOKEN_FORM       = '/\A[0-9a-f]{32}\z/';

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

/**
 * The folder of the stored skeds, with its own .htaccess (private/ is refused by its own and the
 * site's rule already).
 */
function skeds_store(): string
{
    $dir = STORE;
    if (!is_dir($dir) && !@mkdir($dir, 0700, true) && !is_dir($dir)) skeds_refuse(500, 'storage');
    if (!is_file("$dir/.htaccess")) @file_put_contents("$dir/.htaccess", "Require all denied\n");
    return $dir;
}

/**
 * A line in private/logs/skeds.log; the older half goes past 256 KB. No address, token or note is
 * written.
 */
function skeds_log(string $line): void
{
    $folder = SITE_ROOT . '/private/logs';
    if (!is_dir($folder) && !@mkdir($folder, 0700, true) && !is_dir($folder)) return;
    $path = "$folder/skeds.log";
    if (is_file($path) && filesize($path) > LOG_MAX_BYTES) @file_put_contents($path, substr((string) file_get_contents($path), (int) (LOG_MAX_BYTES / 2)), LOCK_EX);
    @file_put_contents($path, gmdate('Y-m-d\TH:i:s\Z') . "  $line\n", FILE_APPEND | LOCK_EX);
}

/**
 * The address as it is hashed: an IPv6 address by its first 64 bits (the rest is the household's to
 * choose).
 */
function skeds_address(): string
{
    $ip = (string) ($_SERVER['REMOTE_ADDR'] ?? '');
    $raw = @inet_pton($ip);
    if ($raw === false) return $ip;
    return strlen($raw) === 16 ? substr($raw, 0, 8) : $raw;
}

/**
 * Count this request against the address and the whole; false when either has used its hour's
 * share. Only hashes are kept.
 */
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

/**
 * The one lock every change of the folder and the board is made under; released when the request
 * ends.
 */
function skeds_lock(string $dir): mixed
{
    $h = @fopen("$dir/lock", 'c');
    if ($h === false || !flock($h, LOCK_EX)) skeds_refuse(500, 'storage');
    return $h;
}

/**
 * The id of a sked when the value is one (12 lowercase hex digits), else null. Only those digits come out, so it can
 * name a file of the folder and nothing outside it: Psalm is told so here, since it cannot follow a pattern.
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

/**
 * The instant of a time of the form 2026-11-14T18:00:00Z, else null (a day or hour that does not
 * exist is no time).
 */
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
    return is_string($value) && preg_match(DIAL_FORM, $value) ? $value : null;
}

/** The note: one line of letters, marks, digits, punctuation, printable ASCII and plain spaces;
 * every other character is removed, runs of spaces and line breaks become one space, cut to 80
 * characters. Null when not UTF-8 text. */
function skeds_note(mixed $value): ?string
{
    if ($value === null) return '';
    if (!is_string($value) || !preg_match('//u', $value)) return null;
    $spaced = (string) preg_replace('/[\x{0009}-\x{000D}\x{0020}\x{0085}\x{00A0}\x{1680}\x{2000}-\x{200A}\x{2028}\x{2029}\x{202F}\x{205F}\x{3000}]+/u', ' ', $value);
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

/**
 * The call without its SSID: the limit of skeds under one call and a blocked call hold for every
 * SSID.
 */
function skeds_base(string $call): string
{
    return explode('-', $call)[0];
}

function skeds_is_blocked(string $call, array $blocked): bool
{
    return in_array($call, $blocked, true) || in_array(skeds_base($call), $blocked, true);
}

/**
 * The stored skeds by id, to come and past, in the order of their start; ones that ended more than
 * KEEP_PAST_SEC ago, the oldest past ones beyond MAX_PAST_KEPT, ones of a blocked call and files that
 * are no sked are removed. Under the lock only.
 */
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
        $good = $from !== null && $to !== null && $from < $to && $call !== null && ($row['id'] ?? null) === $id && skeds_dial($row['dial'] ?? null) !== null && is_string($row['note'] ?? '');
        if (!$good || $to <= $now - KEEP_PAST_SEC || skeds_is_blocked($call, $blocked)) {
            @unlink("$dir/$name");
            continue;
        }
        $found[$id] = ['at' => $from, 'end' => $to] + $row;
    }
    $past = array_filter($found, fn($row) => $row['end'] <= $now);
    if (count($past) > MAX_PAST_KEPT) {
        uasort($past, fn($a, $b) => [$b['end'], $a['id']] <=> [$a['end'], $b['id']]);
        foreach (array_slice($past, MAX_PAST_KEPT, null, true) as $id => $row) {
            @unlink("$dir/$id.json");
            unset($found[$id]);
        }
    }
    uasort($found, fn($a, $b) => [$a['at'], $a['id']] <=> [$b['at'], $b['id']]);
    return $found;
}

/** The stored skeds still to come, by id, in the order of their start. */
function skeds_coming(array $stored, int $now): array
{
    return array_filter($stored, fn($row) => $row['end'] > $now);
}

/** A sked as the board and the past tests show it: never a token. */
function skeds_row(array $row): array
{
    return ['id' => (string) $row['id'], 'call' => (string) $row['call'], 'from' => (string) $row['from'], 'to' => (string) $row['to'], 'dial' => (string) $row['dial'], 'note' => (string) ($row['note'] ?? '')];
}

/** The rows of the board: the skeds to come, at most a hundred. */
function skeds_rows(array $stored, int $now): array
{
    return array_map('skeds_row', array_values(array_slice(skeds_coming($stored, $now), 0, MAX_IN_ALL)));
}

/**
 * The rows of the past tests: the MAX_PAST_TESTS newest tests by their end (then their start, then the
 * dial), each test's rows by id, at most MAX_PAST_ROWS rows.
 */
function skeds_past_rows(array $stored, int $now): array
{
    $tests = [];
    foreach ($stored as $row) {
        if ($row['end'] > $now) continue;
        $tests[$row['from'] . '|' . $row['to'] . '|' . $row['dial']][] = $row;
    }
    uasort($tests, fn($a, $b) => [$b[0]['end'], $b[0]['at'], $a[0]['dial']] <=> [$a[0]['end'], $a[0]['at'], $b[0]['dial']]);
    $rows = [];
    foreach (array_slice($tests, 0, MAX_PAST_TESTS) as $test) {
        usort($test, fn($a, $b) => $a['id'] <=> $b['id']);
        foreach ($test as $row) $rows[] = skeds_row($row);
    }
    return array_slice($rows, 0, MAX_PAST_ROWS);
}

/** The board (BOARD's value) and the past tests (PAST's value) of the stored skeds. */
function skeds_lists(string $dir, int $now): array
{
    $stored = skeds_stored($dir, $now);
    return [
        ['v' => 1, 'written' => skeds_iso($now), 'closed' => is_file("$dir/closed"), 'skeds' => skeds_rows($stored, $now)],
        ['v' => 1, 'written' => skeds_iso($now), 'past' => skeds_past_rows($stored, $now)],
    ];
}

/** Writes one of the served files (a .part, then renamed). */
function skeds_publish(string $path, array $value): void
{
    $json = json_encode($value, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_HEX_TAG | JSON_HEX_AMP);
    $part = $path . '.part';
    if ($json === false || @file_put_contents($part, $json . "\n") === false || !@rename($part, $path)) {
        @unlink($part);
        skeds_refuse(500, 'storage');
    }
}

/** Writes the board and the past tests from the stored skeds; returns both. Under the lock only. */
function skeds_write_board(string $dir, int $now): array
{
    [$board, $past] = skeds_lists($dir, $now);
    skeds_publish(BOARD, $board);
    skeds_publish(PAST, $past);
    return [$board, $past];
}

/**
 * The answer to an accepted request: `head` (ok, and the id of an add), the board, and the past tests
 * only when the request asked for them with "past": true.
 */
function skeds_done(array $in, array $head, array $board, array $past, mixed $lock): never
{
    flock($lock, LOCK_UN);
    skeds_answer(200, $head + ['board' => $board] + (($in['past'] ?? null) === true ? ['past' => $past] : []));
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
    $coming = skeds_coming($stored, $now);
    $fromIso = skeds_iso($from);
    $toIso = skeds_iso($to);
    $mine = 0;
    $ofCall = 0;
    foreach ($coming as $id => $row) {
        if (($row['token'] ?? '') === $hash) {
            if ($row['call'] === $call && $row['from'] === $fromIso && $row['to'] === $toIso && $row['dial'] === $dial && ($row['note'] ?? '') === $note) {
                [$board, $past] = skeds_write_board($dir, $now);
                skeds_done($in, ['ok' => true, 'id' => (string) $id], $board, $past, $lock);
            }
            $mine++;
        }
        if (skeds_base($row['call']) === skeds_base($call)) $ofCall++;
    }
    if ($mine >= MAX_PER_TOKEN || $ofCall >= MAX_PER_CALL || count($coming) >= MAX_IN_ALL) skeds_refuse(409, 'full');
    $id = skeds_new_id($stored);
    skeds_keep($dir, $id, ['id' => $id, 'call' => $call, 'from' => $fromIso, 'to' => $toIso, 'dial' => $dial, 'note' => $note, 'token' => $hash, 'posted' => skeds_iso($now)]);
    [$board, $past] = skeds_write_board($dir, $now);
    skeds_done($in, ['ok' => true, 'id' => $id], $board, $past, $lock);
}

/** A sked of the token's: gone when it has not begun, else ended now and kept as a past test. */
function skeds_remove(string $dir, array $in, int $now): never
{
    $hash = skeds_token_hash($in['token'] ?? null);
    $id = skeds_id($in['id'] ?? null);
    if ($hash === null || $id === null) skeds_refuse(400, 'bad_request');
    $lock = skeds_lock($dir);
    $coming = skeds_coming(skeds_stored($dir, $now), $now);
    $mine = isset($coming[$id]) && hash_equals((string) ($coming[$id]['token'] ?? ''), $hash);
    if (!$mine) {
        flock($lock, LOCK_UN);  // a wrong token or an id that is no longer on the board is counted; the right token is not
        if (!skeds_allowed($dir, skeds_address(), $now)) skeds_refuse(429, 'rate', ['Retry-After: ' . RATE_WINDOW_SEC]);
        if (isset($coming[$id])) skeds_refuse(403, 'not_yours');
        $lock = skeds_lock($dir);
    } elseif ($coming[$id]['at'] < $now) {
        $row = $coming[$id];
        unset($row['at'], $row['end']);
        skeds_keep($dir, $id, ['to' => skeds_iso($now)] + $row);
    } elseif (!@unlink("$dir/$id.json")) {
        skeds_refuse(500, 'storage');
    }
    [$board, $past] = skeds_write_board($dir, $now);
    skeds_done($in, ['ok' => true], $board, $past, $lock);
}

/** Whether a served file holds `value` already, whenever it was written. */
function skeds_serves(string $path, array $value): bool
{
    $served = json_decode((string) @file_get_contents($path), true);
    if (!is_array($served) || !is_string($served['written'] ?? null)) return false;
    $served['written'] = $value['written'];
    return $served === $value;
}

/**
 * The board and the past tests made again from the stored skeds; each is written only when what it
 * says differs from what is served.
 */
function skeds_refresh(string $dir, array $in, int $now): never
{
    $lock = skeds_lock($dir);
    [$board, $past] = skeds_lists($dir, $now);
    if (skeds_serves(BOARD, $board)) $board = json_decode((string) file_get_contents(BOARD), true);
    else skeds_publish(BOARD, $board);
    if (skeds_serves(PAST, $past)) $past = json_decode((string) file_get_contents(PAST), true);
    else skeds_publish(PAST, $past);
    skeds_done($in, ['ok' => true], $board, $past, $lock);
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
    if ($action === 'refresh') skeds_refresh($dir, $in, $now);
    if ($action !== 'add') skeds_refuse(400, 'bad_request');
    skeds_add($dir, $in, $now);
}

try {
    skeds_receive();
} catch (Throwable $e) {
    skeds_log('error: ' . get_class($e) . ': ' . str_replace(["\r", "\n"], ' ', $e->getMessage()));
    skeds_refuse(500, 'storage');
}
