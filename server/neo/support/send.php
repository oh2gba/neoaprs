<?php
/* Send logs of NeoAPRS, served at neo.oh2gba.eu/support/send.php. The Help group of the program's Settings posts here, only when the person presses Send in its dialog:
 *
 *   multipart/form-data: bundle (the support zip), note (what the person wrote), call, version, platform
 *
 * The answer is JSON, {"ok": true, "ref": "NEO-20261103-1015-7F3A"} or {"ok": false, "reason": CODE} with a status that says it too (405 method, 413 too_large, 429 rate, 400 bad_request or
 * not_a_bundle, 500 storage). The file is kept in private/support/ of this site (see PRIVATE below) as REF.zip with REF.json beside it (time, call, version, platform, size, note), and one plain e-mail
 * goes to the project with the reference, the call, the version, the platform, the size and the note; the zip itself is not mailed. server/support-fetch.sh brings new ones to the developer's computer.
 *
 * What is kept: the zip, and the call, version, platform and note as cleaned here (a call is letters, digits and dashes, 12 at most; the note is text, 2000 characters at most). The sender's address is
 * never written down: it is hashed under a salt that only this folder knows, for the rate limit (5 files an hour from one address, 60 an hour in all), and the hash is forgotten after the hour.
 *
 * The rules every application on the account keeps (oh2gba/SHARED-HOST.md): a body over 20 MB is refused before anything is read, the work is a few file operations, and a failure of the mail is
 * logged (private/logs/support.log) and never fails the upload. `SUPPORT_DIR` (environment) moves the folder, and a function `support_send_mail` defined before this file runs (the tests' stand-in for mail()) replaces the mail. */
declare(strict_types=1);

ini_set('display_errors', '0');
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');

const SUPPORT_TO       = 'neoaprs@oh2gba.eu';
const SUPPORT_FROM     = 'NeoAPRS <noreply@oh2gba.eu>';          // the apex, which the domain's SPF record covers (as the status application's mails)
const MAX_BODY         = 20 * 1024 * 1024;
const MAX_NOTE         = 2000;
const MAX_MEMBERS      = 100;
const MAX_DIRECTORY    = 256 * 1024;                              // of the zip's list of members
const RATE_PER_ADDRESS = 5;
const RATE_IN_ALL      = 60;
const RATE_WINDOW_SEC  = 3600;
const LOG_MAX_BYTES    = 256 * 1024;                              // of the log (oh2gba/SHARED-HOST.md: each application logs under its own private/logs/, each file capped at 256 KB)
// The members of a bundle (neoaprs/cli/supportreadme.py FILE_HELP): the files it holds by name, the logs, and the `.error.txt` of a part that could not be made.
const MEMBER_NAME = '~^(README\.txt|summary\.txt|settings\.json|state\.json|doctor\.txt|database\.txt|packets\.txt|page\.json|page-errors\.json|[A-Za-z0-9_.-]+\.error\.txt|logs/|logs/[A-Za-z0-9_.-]+)$~';

/** Answers the JSON and ends. */
function support_answer(int $status, array $body, array $headers = []): never
{
    http_response_code($status);
    foreach ($headers as $line) header($line);
    echo json_encode($body, JSON_UNESCAPED_SLASHES), "\n";
    exit;
}

function support_refuse(int $status, string $reason, array $headers = []): never
{
    support_answer($status, ['ok' => false, 'reason' => $reason], $headers);
}

/** Where the files are kept: private/support/ beside this folder, which Apache refuses to serve (private/.htaccess, and the rule of .htaccess); one more .htaccess is written in the folder itself. */
function support_dir(): string
{
    $dir = getenv('SUPPORT_DIR') ?: dirname(__DIR__) . '/private/support';
    if (!is_dir($dir) && !@mkdir($dir, 0700, true) && !is_dir($dir)) support_refuse(500, 'storage');
    if (!is_file("$dir/.htaccess")) @file_put_contents("$dir/.htaccess", "Require all denied\n");
    return $dir;
}

/** A line in the log, private/logs/support.log beside the folder of the files; the older half goes when it has grown past 256 KB. No address and no note are written to it. */
function support_log(string $dir, string $line): void
{
    $folder = dirname($dir) . '/logs';
    if (!is_dir($folder) && !@mkdir($folder, 0700, true) && !is_dir($folder)) return;
    $path = "$folder/support.log";
    if (is_file($path) && filesize($path) > LOG_MAX_BYTES) @file_put_contents($path, substr((string) file_get_contents($path), (int) (LOG_MAX_BYTES / 2)), LOCK_EX);
    @file_put_contents($path, gmdate('Y-m-d\TH:i:s\Z') . "  $line\n", FILE_APPEND | LOCK_EX);
}

/** The address as it is hashed: an IPv6 address by its first 64 bits (the rest is the household's to choose). */
function support_address(): string
{
    $ip = (string) ($_SERVER['REMOTE_ADDR'] ?? '');
    $raw = @inet_pton($ip);
    if ($raw === false) return $ip;
    return strlen($raw) === 16 ? substr($raw, 0, 8) : $raw;
}

/** Counts this request against the address and the whole; false when either has used its share of the last hour. Only hashes are kept, and only for the hour. */
function support_allowed(string $dir, string $address, int $now): bool
{
    $saltFile = "$dir/salt";
    if (!is_file($saltFile)) @file_put_contents($saltFile, bin2hex(random_bytes(16)), LOCK_EX);
    $key = substr(hash('sha256', trim((string) @file_get_contents($saltFile)) . '|' . $address), 0, 16);
    $h = @fopen("$dir/rate.json", 'c+');
    if ($h === false) support_refuse(500, 'storage');
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

/** The names of the members of the zip at `path`, read from its central directory (no zip extension is needed); null when it is no zip, or when the list is not what a zip of ours has. */
function support_members(string $path): ?array
{
    $size = filesize($path);
    $h = @fopen($path, 'rb');
    if ($h === false || $size === false || $size < 22) return null;
    try {
        if (fread($h, 4) !== "PK\x03\x04") return null;
        $tailLen = min($size, 22 + 65535);
        fseek($h, $size - $tailLen);
        $tail = (string) fread($h, $tailLen);
        $end = strrpos($tail, "PK\x05\x06");
        if ($end === false || strlen($tail) < $end + 22) return null;
        $count  = unpack('v', substr($tail, $end + 10, 2))[1];
        $length = unpack('V', substr($tail, $end + 12, 4))[1];
        $offset = unpack('V', substr($tail, $end + 16, 4))[1];
        if ($count < 1 || $count > MAX_MEMBERS || $length > MAX_DIRECTORY || $offset + $length > $size) return null;
        fseek($h, $offset);
        $dir = (string) fread($h, $length);
    } finally {
        fclose($h);
    }
    $names = [];
    $at = 0;
    while (count($names) < $count) {
        if (substr($dir, $at, 4) !== "PK\x01\x02" || strlen($dir) < $at + 46) return null;
        $n = unpack('v', substr($dir, $at + 28, 2))[1];
        $extra = unpack('v', substr($dir, $at + 30, 2))[1];
        $comment = unpack('v', substr($dir, $at + 32, 2))[1];
        $name = substr($dir, $at + 46, $n);
        if (strlen($name) !== $n) return null;
        $names[] = $name;
        $at += 46 + $n + $extra + $comment;
    }
    return $names;
}

/** True when the members look like a NeoAPRS bundle: summary.txt, and only the names a bundle has. */
function support_is_bundle(array $names): bool
{
    if (!in_array('summary.txt', $names, true)) return false;
    foreach ($names as $name) {
        if (!preg_match(MEMBER_NAME, $name)) return false;
    }
    return true;
}

/** A word of the form: only the characters in `$keep`, at most `$max` of them. */
function support_clean(mixed $value, string $keep, int $max): string
{
    return is_string($value) ? substr((string) preg_replace('/[^' . $keep . ']/', '', $value), 0, $max) : '';
}

/** The note: text. Invalid UTF-8 and control characters other than the line break and the tab are dropped, the line breaks are \n, and it is cut to 2000 characters. */
function support_note(mixed $value): string
{
    if (!is_string($value)) return '';
    $text = str_replace(["\r\n", "\r"], "\n", $value);
    $clean = preg_replace('/[^\x{0009}\x{000A}\x{0020}-\x{007E}\x{00A0}-\x{10FFFF}]/u', '', $text);
    if ($clean === null) $clean = (string) preg_replace('/[^\x09\x0A\x20-\x7E]/', '', $text);       // (not UTF-8 at all: its ASCII is kept)
    $chars = preg_split('//u', $clean, MAX_NOTE + 1, PREG_SPLIT_NO_EMPTY);
    return trim(implode('', array_slice($chars === false ? [] : $chars, 0, MAX_NOTE)));
}

/** NEO-20261103-1015-7F3A, not yet in use in `$dir`. */
function support_reference(string $dir, int $now): string
{
    for ($i = 0; $i < 50; $i++) {
        $ref = 'NEO-' . gmdate('Ymd-Hi', $now) . '-' . strtoupper(bin2hex(random_bytes(2)));
        if (!file_exists("$dir/$ref.zip") && !file_exists("$dir/$ref.json")) return $ref;
    }
    support_refuse(500, 'storage');
}

if (!function_exists('support_send_mail')) {
    /** The one plain mail to the project, the way the status application sends its alerts. Everything in the headers and the subject is ours; what a person wrote is in the body only. */
    function support_send_mail(string $subject, string $body): bool
    {
        if (preg_match('/[\r\n]/', $subject)) return false;
        $headers = 'From: ' . SUPPORT_FROM . "\r\nContent-Type: text/plain; charset=utf-8\r\nX-Mailer: neoaprs-support\r\n";
        return @mail(SUPPORT_TO, $subject, $body, $headers);
    }
}

function support_receive(): never
{
    if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') support_refuse(405, 'method', ['Allow: POST']);
    $length = (int) ($_SERVER['CONTENT_LENGTH'] ?? 0);
    $postMax = ini_parse_quantity((string) ini_get('post_max_size'));
    if ($length > MAX_BODY || ($postMax > 0 && $length > $postMax)) support_refuse(413, 'too_large');

    $now = time();
    $dir = support_dir();
    if (!support_allowed($dir, support_address(), $now)) support_refuse(429, 'rate', ['Retry-After: ' . RATE_WINDOW_SEC]);

    $file = $_FILES['bundle'] ?? null;
    if (!is_array($file) || !is_string($file['tmp_name'] ?? null)) support_refuse(400, 'bad_request');
    if (in_array($file['error'], [UPLOAD_ERR_INI_SIZE, UPLOAD_ERR_FORM_SIZE], true)) support_refuse(413, 'too_large');
    if ($file['error'] !== UPLOAD_ERR_OK || !is_uploaded_file($file['tmp_name'])) support_refuse(400, 'bad_request');
    $size = (int) filesize($file['tmp_name']);
    if ($size > MAX_BODY) support_refuse(413, 'too_large');
    $names = support_members($file['tmp_name']);
    if ($names === null || !support_is_bundle($names)) support_refuse(400, 'not_a_bundle');

    $call     = support_clean($_POST['call'] ?? '', 'A-Za-z0-9-', 12);
    $version  = support_clean($_POST['version'] ?? '', '0-9A-Za-z._+-', 20);
    $platform = support_clean($_POST['platform'] ?? '', '0-9A-Za-z._-', 40);
    $note     = support_note($_POST['note'] ?? '');

    $ref = support_reference($dir, $now);
    if (!@move_uploaded_file($file['tmp_name'], "$dir/$ref.zip")) support_refuse(500, 'storage');
    @chmod("$dir/$ref.zip", 0600);
    $meta = ['ref' => $ref, 'time' => gmdate('Y-m-d\TH:i:s\Z', $now), 'call' => $call, 'version' => $version, 'platform' => $platform, 'size' => $size, 'note' => $note];
    $json = json_encode($meta, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT | JSON_INVALID_UTF8_SUBSTITUTE);
    if ($json === false || @file_put_contents("$dir/$ref.json.part", $json . "\n") === false || !@rename("$dir/$ref.json.part", "$dir/$ref.json")) {
        @unlink("$dir/$ref.zip");
        support_refuse(500, 'storage');
    }
    @chmod("$dir/$ref.json", 0600);

    $subject = 'NeoAPRS logs ' . $ref . ($call !== '' ? ' from ' . $call : '');
    $body = "A NeoAPRS support file was sent.\n\n"
          . "Reference: $ref\nCall:      " . ($call ?: '-') . "\nVersion:   " . ($version ?: '-') . "\nPlatform:  " . ($platform ?: '-') . "\n"
          . 'Size:      ' . max(1, intdiv($size, 1024)) . " KB\nTime:      " . gmdate('Y-m-d H:i', $now) . " UTC\n\n"
          . "Note:\n" . ($note !== '' ? $note : '(none)') . "\n\n"
          . "The file is on the server; server/support-fetch.sh brings it.\n";
    try {
        $mailed = support_send_mail($subject, $body);
    } catch (Throwable $e) {
        $mailed = false;
    }
    if (!$mailed) support_log($dir, "the mail for $ref was not sent");

    support_answer(200, ['ok' => true, 'ref' => $ref]);
}

try {
    support_receive();
} catch (Throwable $e) {
    $dir = getenv('SUPPORT_DIR') ?: dirname(__DIR__) . '/private/support';
    if (is_dir($dir)) support_log($dir, 'error: ' . get_class($e) . ': ' . str_replace(["\r", "\n"], ' ', $e->getMessage()));
    support_refuse(500, 'storage');
}
