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
 * ago, the oldest past ones beyond 1000, and those of a blocked call are left out of both files at
 * once and removed by the first write after ten minutes since the last such cleanup (the file
 * `cleaned`). The sender's address is never written down: it is hashed under a salt only this folder
 * knows, for the rate limit (10 adds an hour from one address, 60 an hour in all; an add counts once it
 * is well formed and within the times, and so does a remove with a wrong token or of an id that is
 * gone; a remove with the right token does not). A refresh is counted apart (refresh.json): 60 an hour
 * from one address and no share in all, so that a flood from elsewhere cannot keep the moderator from
 * remaking the board. The hash is forgotten after the hour. A refresh writes each file only when what
 * it says has changed.
 *
 * Moderation (server/skeds.sh, over SFTP): a file `closed` in the folder makes every add answer `closed`
 * and the board say "closed": true; `blocked.txt` holds a call per line whose adds answer `closed` and
 * whose skeds, past ones too, are removed (the chat, api/v1/chat.php, reads the same list). Removing a
 * file there and posting a refresh makes the board again. What the endpoints share is in
 * private/endpoint.php. */
declare(strict_types=1);

require __DIR__ . '/../../private/endpoint.php';
neo_headers();

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
const RATE_REFRESH     = 60;      // refreshes an hour from one address, counted apart from the adds and never in all
const CLEAN_EVERY_SEC  = 600;     // the removal of old, surplus and blocked files, at most this often
const TIME_FORM        = '/\A\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\z/';
const DIAL_FORM        = '/\A\d{1,2}\.\d{3,4} MHz (USB|LSB)\z/';  // as neoaprs/versions.py reads a dial and the HF box shows it
const ID_FORM          = '/\A[0-9a-f]{12}\z/';
const NOTE_KEPT        = '\x{0020}-\x{007E}\p{L}\p{M}\p{N}\p{P}';  // what a note keeps: printable ASCII, letters, marks, digits, punctuation

/**
 * Count this request against the address and the whole in `file`; false when either has used its
 * hour's share.
 */
function skeds_allowed(string $dir, string $address, int $now, string $file = 'rate.json', int $per = RATE_PER_ADDRESS, int $inAll = RATE_IN_ALL): bool
{
    return neo_allowed($dir, $address, $now, $file, $per, $inAll, RATE_WINDOW_SEC);
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

function skeds_dial(mixed $value): ?string
{
    return is_string($value) && preg_match(DIAL_FORM, $value) ? $value : null;
}

/** The note: one line of letters, marks, digits, punctuation, printable ASCII and plain spaces (`neo_line`), at
 * most 80 characters; none is empty. Null when not UTF-8 text. */
function skeds_note(mixed $value): ?string
{
    return $value === null ? '' : neo_line($value, MAX_NOTE, NOTE_KEPT);
}

/**
 * Whether the files that are no longer listed are removed now: at most every CLEAN_EVERY_SEC (the
 * file `cleaned` holds when last), so that a write does not unlink at every request. Under the lock only.
 */
function skeds_clean_due(string $dir, int $now): bool
{
    $at = @filemtime("$dir/cleaned");
    if ($at !== false && $now - $at < CLEAN_EVERY_SEC && $at <= $now) return false;
    @touch("$dir/cleaned", $now);
    return true;
}

/**
 * The stored skeds by id, to come and past, in the order of their start; ones that ended more than
 * KEEP_PAST_SEC ago, the oldest past ones beyond MAX_PAST_KEPT, ones of a blocked call and files that
 * are no sked are left out, and removed when a cleanup is due. Under the lock only.
 */
function skeds_stored(string $dir, int $now): array
{
    $clean = skeds_clean_due($dir, $now);
    $blocked = neo_blocked();
    $found = [];
    foreach ((array) @scandir($dir) as $name) {
        if (!is_string($name) || !preg_match('/^([0-9a-f]{12})\.json$/', $name, $m)) continue;
        $id = $m[1];
        $row = json_decode((string) @file_get_contents("$dir/$name"), true);
        $from = is_array($row) ? skeds_time($row['from'] ?? null) : null;
        $to = is_array($row) ? skeds_time($row['to'] ?? null) : null;
        $call = is_array($row) ? neo_call($row['call'] ?? null) : null;
        $good = $from !== null && $to !== null && $from < $to && $call !== null && ($row['id'] ?? null) === $id && skeds_dial($row['dial'] ?? null) !== null && is_string($row['note'] ?? '');
        if (!$good || $to <= $now - KEEP_PAST_SEC || neo_is_blocked($call, $blocked)) {
            if ($clean) @unlink("$dir/$name");
            continue;
        }
        $found[$id] = ['at' => $from, 'end' => $to] + $row;
    }
    $past = array_filter($found, fn($row) => $row['end'] <= $now);
    if (count($past) > MAX_PAST_KEPT) {
        uasort($past, fn($a, $b) => $b['end'] <=> $a['end'] ?: strcmp((string) $a['id'], (string) $b['id']));
        foreach (array_slice($past, MAX_PAST_KEPT, null, true) as $id => $row) {
            if ($clean) @unlink("$dir/$id.json");
            unset($found[$id]);
        }
    }
    uasort($found, fn($a, $b) => $a['at'] <=> $b['at'] ?: strcmp((string) $a['id'], (string) $b['id']));
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
    uasort($tests, fn($a, $b) => $b[0]['end'] <=> $a[0]['end'] ?: $b[0]['at'] <=> $a[0]['at'] ?: strcmp((string) $a[0]['dial'], (string) $b[0]['dial']));
    $rows = [];
    foreach (array_slice($tests, 0, MAX_PAST_TESTS) as $test) {
        usort($test, fn($a, $b) => strcmp((string) $a['id'], (string) $b['id']));
        foreach ($test as $row) $rows[] = skeds_row($row);
    }
    return array_slice($rows, 0, MAX_PAST_ROWS);
}

/** The board (BOARD's value) and the past tests (PAST's value) of the stored skeds. */
function skeds_lists(string $dir, int $now): array
{
    $stored = skeds_stored($dir, $now);
    return [
        ['v' => 1, 'written' => neo_iso($now), 'closed' => is_file("$dir/closed"), 'skeds' => skeds_rows($stored, $now)],
        ['v' => 1, 'written' => neo_iso($now), 'past' => skeds_past_rows($stored, $now)],
    ];
}

/** Writes the board and the past tests from the stored skeds; returns both. Under the lock only. */
function skeds_write_board(string $dir, int $now): array
{
    [$board, $past] = skeds_lists($dir, $now);
    neo_publish(BOARD, $board);
    neo_publish(PAST, $past);
    return [$board, $past];
}

/**
 * The answer to an accepted request: `head` (ok, and the id of an add), the board, and the past tests
 * only when the request asked for them with "past": true.
 */
function skeds_done(array $in, array $head, array $board, array $past, mixed $lock): never
{
    flock($lock, LOCK_UN);
    neo_answer(200, $head + ['board' => $board] + (($in['past'] ?? null) === true ? ['past' => $past] : []));
}

/** Writes one sked's file (a .part, then renamed). */
function skeds_keep(string $dir, string $id, array $row): void
{
    $json = json_encode($row, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
    $part = "$dir/$id.json.part";
    if ($json === false || @file_put_contents($part, $json . "\n") === false || !@rename($part, "$dir/$id.json")) {
        @unlink($part);
        neo_refuse(500, 'storage');
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
    if (is_file("$dir/closed")) neo_refuse(403, 'closed');
    $hash = neo_token_hash($in['token'] ?? null);
    $call = neo_call($in['call'] ?? null);
    $from = skeds_time($in['from'] ?? null);
    $to = skeds_time($in['to'] ?? null);
    $dial = skeds_dial($in['dial'] ?? null);
    $note = skeds_note($in['note'] ?? null);
    if ($hash === null || $call === null || $from === null || $to === null || $dial === null || $note === null || $to <= $from) neo_refuse(400, 'bad_request');
    if (neo_is_blocked($call, neo_blocked())) neo_refuse(403, 'closed');
    if ($to <= $now) neo_refuse(422, 'past');
    if ($to - $from > MAX_LENGTH_SEC) neo_refuse(422, 'too_long');
    if ($from > $now + MAX_AHEAD_SEC) neo_refuse(422, 'too_far');
    if (!skeds_allowed($dir, neo_address(), $now)) neo_refuse(429, 'rate', ['Retry-After: ' . RATE_WINDOW_SEC]);

    $lock = neo_lock($dir);
    $stored = skeds_stored($dir, $now);
    $coming = skeds_coming($stored, $now);
    $fromIso = neo_iso($from);
    $toIso = neo_iso($to);
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
        if (neo_base($row['call']) === neo_base($call)) $ofCall++;
    }
    if ($mine >= MAX_PER_TOKEN || $ofCall >= MAX_PER_CALL || count($coming) >= MAX_IN_ALL) neo_refuse(409, 'full');
    $id = skeds_new_id($stored);
    skeds_keep($dir, $id, ['id' => $id, 'call' => $call, 'from' => $fromIso, 'to' => $toIso, 'dial' => $dial, 'note' => $note, 'token' => $hash, 'posted' => neo_iso($now)]);
    [$board, $past] = skeds_write_board($dir, $now);
    skeds_done($in, ['ok' => true, 'id' => $id], $board, $past, $lock);
}

/** A sked of the token's: gone when it has not begun, else ended now and kept as a past test. */
function skeds_remove(string $dir, array $in, int $now): never
{
    $hash = neo_token_hash($in['token'] ?? null);
    $id = skeds_id($in['id'] ?? null);
    if ($hash === null || $id === null) neo_refuse(400, 'bad_request');
    $lock = neo_lock($dir);
    $coming = skeds_coming(skeds_stored($dir, $now), $now);
    $mine = isset($coming[$id]) && hash_equals((string) ($coming[$id]['token'] ?? ''), $hash);
    if (!$mine) {
        flock($lock, LOCK_UN);  // a wrong token or an id that is no longer on the board is counted; the right token is not
        if (!skeds_allowed($dir, neo_address(), $now)) neo_refuse(429, 'rate', ['Retry-After: ' . RATE_WINDOW_SEC]);
        if (isset($coming[$id])) neo_refuse(403, 'not_yours');
        $lock = neo_lock($dir);
    } elseif ($coming[$id]['at'] < $now) {
        $row = $coming[$id];
        unset($row['at'], $row['end']);
        skeds_keep($dir, $id, ['to' => neo_iso($now)] + $row);
    } elseif (!@unlink("$dir/$id.json")) {
        neo_refuse(500, 'storage');
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
    if (!skeds_allowed($dir, neo_address(), $now, 'refresh.json', RATE_REFRESH, PHP_INT_MAX)) {
        neo_refuse(429, 'rate', ['Retry-After: ' . RATE_WINDOW_SEC]);
    }
    $lock = neo_lock($dir);
    [$board, $past] = skeds_lists($dir, $now);
    if (skeds_serves(BOARD, $board)) $board = json_decode((string) file_get_contents(BOARD), true);
    else neo_publish(BOARD, $board);
    if (skeds_serves(PAST, $past)) $past = json_decode((string) file_get_contents(PAST), true);
    else neo_publish(PAST, $past);
    skeds_done($in, ['ok' => true], $board, $past, $lock);
}

function skeds_receive(): never
{
    $in = neo_request(MAX_BODY);
    $now = time();
    $dir = neo_folder(STORE);
    $action = $in['action'] ?? null;
    if ($action === 'remove') skeds_remove($dir, $in, $now);
    if ($action === 'refresh') skeds_refresh($dir, $in, $now);
    if ($action !== 'add') neo_refuse(400, 'bad_request');
    skeds_add($dir, $in, $now);
}

try {
    skeds_receive();
} catch (Throwable $e) {
    neo_log('skeds', 'error: ' . get_class($e) . ': ' . str_replace(["\r", "\n"], ' ', $e->getMessage()));
    neo_refuse(500, 'storage');
}
