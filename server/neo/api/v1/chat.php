<?php
/* The chat of NeoAPRS, served at neo.oh2gba.eu/api/v1/chat.php: one room where the operators of the
 * HF tests tab say a line to each other, over the Internet, never on the air. The program posts here
 * only a line its operator wrote.
 *
 * Reading is not done here: every accepted line writes the chat to chat.json in the site root (CHAT),
 * which Apache serves as a static file with its ETag and Last-Modified, so that a reader that sends
 * them back is answered 304 with no body while nothing changed. The chat is {"v": 1, "written": TIME,
 * "closed": false, "lines": [{"id", "at", "call", "text"}, ...]}, oldest first: the newest 100 lines,
 * never a token or its hash. An id is a whole number that grows by one
 * with each line accepted, so a reader knows which lines are new to it.
 *
 * Writing is a POST of application/json, at most 1024 bytes, refused from its Content-Length before
 * anything is read:
 *
 *   {"action": "say", "token": "<32 hex>", "call": "OH2GBA", "text": "QRV on 7.0541"}  -> {"ok": true, "id": ID, "chat": CHAT}
 *   {"action": "refresh"}                                                         -> {"ok": true, "chat": CHAT}
 *
 * A refusal is {"ok": false, "reason": CODE} with the board's codes and statuses: 405 method,
 * 413 too_large, 415 bad_request (not application/json), 400 bad_request, 429 rate, 403 closed (the
 * chat closed or the call blocked), 500 storage.
 *
 * Few limits: the call has the form of an amateur call (as the board's), the text is one line of at
 * most 200 characters, its control and invisible characters removed and its white space made single
 * spaces, and not empty. A brake stops a flood: 6 lines a minute from one address
 * and 200 a minute in all. A line is never removed by a request.
 *
 * What is kept: every line in private/chat/lines.json with the hash of the token that said it and the
 * next id, written to a .part and renamed under one lock (the file `lock`), as chat.json is, so that
 * two writers never lose a line and a reader never gets half a file. The address is hashed under the
 * folder's own salt for the brake and forgotten after the minute; a refresh is counted apart
 * (refresh.json, 60 an hour from one address and 2000 from everyone).
 *
 * Moderation (server/chat.sh, over SFTP): a file `closed` in private/chat/ makes every line answer
 * `closed` and the chat say "closed": true; `removed.txt` there holds an id per line that is taken
 * out; the board's private/skeds/blocked.txt holds the calls whose lines are refused and taken out.
 * A refresh after a change writes the chat again. What the endpoints share is in
 * private/endpoint.php. */
declare(strict_types=1);

ini_set('display_errors', '0');
if (!is_file(__DIR__ . '/../../private/endpoint.php')) {
    http_response_code(503);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    exit('{"ok":false,"reason":"storage"}');
}
require __DIR__ . '/../../private/endpoint.php';
neo_headers();

const CHAT             = SITE_ROOT . '/chat.json';
const STORE            = SITE_ROOT . '/private/chat';
const MAX_BODY         = 1024;
const MAX_TEXT         = 200;
// the history, so that a station that was offline still finds what was said: the newest lines, kept and served
const MAX_LINES        = 100;
const RATE_PER_ADDRESS = 6;       // lines a minute from one address
const RATE_IN_ALL      = 200;     // lines a minute from everyone
const RATE_WINDOW_SEC  = 60;
const RATE_REFRESH     = 60;      // refreshes an hour from one address, counted apart from the lines
const REFRESH_IN_ALL   = 2000;    // refreshes an hour from everyone
const TEXT_KEPT        = '\P{C}';  // what a line keeps: every character but the control, format, private and unassigned ones
const TIME_FORM        = '/\A\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\z/';

/** The ids the owner took out (removed.txt, one on each line). */
function chat_removed(string $dir): array
{
    $lines = @file("$dir/removed.txt", FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    return $lines === false ? [] : array_values(array_filter(array_map(fn($l) => trim((string) $l), $lines), fn($l) => ctype_digit($l)));
}

/**
 * The stored lines, oldest first, without those of a blocked call, taken out by the owner or not
 * well formed, at most MAX_LINES; and the next id. Under the lock only.
 */
function chat_stored(string $dir): array
{
    $kept = json_decode((string) @file_get_contents("$dir/lines.json"), true);
    $kept = is_array($kept) ? $kept : [];
    $blocked = neo_blocked();
    $removed = chat_removed($dir);
    $next = is_int($kept['next'] ?? null) && $kept['next'] > 0 ? $kept['next'] : 1;
    $lines = [];
    foreach (is_array($kept['lines'] ?? null) ? $kept['lines'] : [] as $line) {
        if (!is_array($line) || !is_int($line['id'] ?? null) || !is_string($line['at'] ?? null) || !preg_match(TIME_FORM, $line['at'])) continue;
        $call = neo_call($line['call'] ?? null);
        if ($call === null || !is_string($line['text'] ?? null)) continue;
        $next = max($next, $line['id'] + 1);
        if (neo_is_blocked($call, $blocked) || in_array((string) $line['id'], $removed, true)) continue;
        $lines[] = $line;
    }
    usort($lines, fn($a, $b) => $a['id'] <=> $b['id']);
    return [array_slice($lines, -MAX_LINES), $next];
}

/** The chat as it is served: never a token. */
function chat_value(string $dir, array $lines, int $now): array
{
    $shown = array_map(fn($l) => ['id' => $l['id'], 'at' => (string) $l['at'], 'call' => (string) $l['call'], 'text' => (string) $l['text']], $lines);
    return ['v' => 1, 'written' => neo_iso($now), 'closed' => is_file("$dir/closed"), 'lines' => $shown];
}

/** Writes the kept lines (a .part, then renamed). Under the lock only. */
function chat_keep(string $dir, array $lines, int $next): void
{
    $json = json_encode(['next' => $next, 'lines' => $lines], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    $part = "$dir/lines.json.part";
    if ($json === false || @file_put_contents($part, $json . "\n") === false || !@rename($part, "$dir/lines.json")) {
        @unlink($part);
        neo_refuse(500, 'storage');
    }
    @chmod("$dir/lines.json", 0600);
}

function chat_say(string $dir, array $in, int $now): never
{
    if (is_file("$dir/closed")) neo_refuse(403, 'closed');
    $hash = neo_token_hash($in['token'] ?? null);
    $call = neo_call($in['call'] ?? null);
    $text = neo_line($in['text'] ?? null, MAX_TEXT, TEXT_KEPT);
    if ($hash === null || $call === null || $text === null || $text === '') neo_refuse(400, 'bad_request');
    if (neo_is_blocked($call, neo_blocked())) neo_refuse(403, 'closed');
    if (!neo_allowed($dir, neo_address(), $now, 'rate.json', RATE_PER_ADDRESS, RATE_IN_ALL, RATE_WINDOW_SEC)) {
        neo_refuse(429, 'rate', ['Retry-After: ' . RATE_WINDOW_SEC]);
    }
    $lock = neo_lock($dir);
    [$lines, $next] = chat_stored($dir);
    $lines[] = ['id' => $next, 'at' => neo_iso($now), 'call' => $call, 'text' => $text, 'token' => $hash];
    $lines = array_slice($lines, -MAX_LINES);
    chat_keep($dir, $lines, $next + 1);
    $chat = chat_value($dir, $lines, $now);
    neo_publish(CHAT, $chat);
    flock($lock, LOCK_UN);
    neo_answer(200, ['ok' => true, 'id' => $next, 'chat' => $chat]);
}

/** The chat written again from the kept lines, only when what it says differs from what is served. */
function chat_refresh(string $dir, int $now): never
{
    if (!neo_allowed($dir, neo_address(), $now, 'refresh.json', RATE_REFRESH, REFRESH_IN_ALL, 3600)) {
        neo_refuse(429, 'rate', ['Retry-After: 3600']);
    }
    $lock = neo_lock($dir);
    [$lines, $next] = chat_stored($dir);
    chat_keep($dir, $lines, $next);
    $chat = chat_value($dir, $lines, $now);
    $served = json_decode((string) @file_get_contents(CHAT), true);
    if (is_array($served) && is_string($served['written'] ?? null) && array_merge($served, ['written' => $chat['written']]) === $chat) {
        $chat = $served;
    } else {
        neo_publish(CHAT, $chat);
    }
    flock($lock, LOCK_UN);
    neo_answer(200, ['ok' => true, 'chat' => $chat]);
}

function chat_receive(): never
{
    $in = neo_request(MAX_BODY);
    $now = time();
    $dir = neo_folder(STORE);
    $action = $in['action'] ?? null;
    if ($action === 'refresh') chat_refresh($dir, $now);
    if ($action !== 'say') neo_refuse(400, 'bad_request');
    chat_say($dir, $in, $now);
}

try {
    chat_receive();
} catch (Throwable $e) {
    neo_log('chat', 'error: ' . get_class($e) . ': ' . str_replace(["\r", "\n"], ' ', $e->getMessage()));
    neo_refuse(500, 'storage');
}
