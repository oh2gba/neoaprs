<?php
/* Send logs of NeoAPRS, served at neo.oh2gba.eu/support/send.php. The Help group of the program's Settings
 * posts here only when the person presses Send in its dialog:
 *
 *   multipart/form-data: bundle (the support zip), note (what the person wrote), email (an address
 *   for a reply, optional), call, version, platform
 *
 * A form with no file and no `bundle` is the note alone (the person took the file off): the note must have
 * words then, REF.json is kept without a zip (`"file": false`, size 0), and the mail says in its first line
 * that no file came. It is counted and bounded as a file is. A form with a file under any other name, and a
 * note in a body that is not multipart/form-data, are refused.
 *
 * The answer is JSON, {"ok": true, "ref": "NEO-20261103-1015-7F3A"} or {"ok": false, "reason": CODE} with a
 * matching status (405 method, 413 too_large, 429 rate, 400 bad_request or not_a_bundle, 500 storage). The
 * file is kept in private/support/ (see PRIVATE) as REF.zip with REF.json beside it (time, call, email,
 * version, platform, size, note), and one plain e-mail with the reference, call, email, version, platform, size
 * and note goes to the project; the zip itself is not mailed. server/support-fetch.sh brings new ones to the developer.
 *
 * What is kept: the zip, and the call, email, version, platform and note as cleaned here (a call is letters,
 * digits and dashes, 12 at most; the note is text, 2000 characters at most; an email that is not an address,
 * as neoaprs/web/supportsend.py reply_address reads one, is kept empty and the report is taken all the same). The sender's address is never
 * written down: it is hashed under a salt only this folder knows, for the rate limits, and the hash is
 * forgotten after the hour. Only a request that stores a file counts against the shared limit (5 files an
 * hour from one address, 60 an hour in all, a note alone counting as a file); a request refused as no
 * bundle counts against its own address alone (20 an hour), so nobody can use up the others' share with
 * requests that store nothing.
 *
 * What the folder holds is bounded: a file is 10 MB at most (a real station's bundle is a megabyte or two:
 * logs are cut to 12 MB of text before zipping, and 12 MB of the least compressible log lines weigh 7 MB
 * zipped), the folder 200 MB and 300 references (a bundle with its json, or the json of a note alone), and
 * what is older than 30 days is removed at each accepted upload. When the folder is full the answer is
 * `rate` (the program says: try again later), the log says why, and one mail tells the project the first
 * time (until a file is stored again). Counting and storing a file are one step under a lock, so
 * simultaneous uploads cannot pass the cap together.
 *
 * The rules every application on the account keeps (oh2gba/SHARED-HOST.md): a body over 10 MB is refused
 * before anything is read, the work is a few file operations, and a mail failure is logged
 * (private/logs/support.log) and never fails the upload. `SUPPORT_DIR` (environment) moves the folder, and
 * a function `support_send_mail` defined before this file runs (the tests' stand-in for mail()) replaces the mail. */
declare(strict_types=1);

ini_set('display_errors', '0');
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');

const SUPPORT_TO       = 'neo@oh2gba.eu';
const SUPPORT_FROM     = 'NeoAPRS <noreply@oh2gba.eu>';  // the apex, which the domain's SPF record covers
const MAX_FILE         = 10 * 1024 * 1024;                        // of the bundle
const MAX_BODY         = MAX_FILE + 64 * 1024;                    // of the request: the file and the few small fields beside it
const FOLDER_MAX_BYTES = 200 * 1024 * 1024;                       // of the stored files together
const FOLDER_MAX_FILES = 300;                                     // references: a bundle with its json, or the json of a note alone
const KEEP_DAYS        = 30;
const MAX_NOTE         = 2000;
const MAX_EMAIL        = 254;                                     // characters
const MAX_MEMBERS      = 40;                                      // a bundle has the dozen fixed names, a few error files and the log with its rotated copies
const MAX_UNPACKED     = 50 * 1024 * 1024;                        // the members' sizes once unpacked, together
const MAX_DIRECTORY    = 256 * 1024;                              // of the zip's list of members
const RATE_PER_ADDRESS = 5;                                        // stored files
const RATE_IN_ALL      = 60;
const BAD_PER_ADDRESS  = 20;                                      // refused requests
const BAD_KEYS_MAX     = 2000;                                    // addresses whose refusals are remembered at once
const RATE_WINDOW_SEC  = 3600;
const LOG_MAX_BYTES    = 256 * 1024;  // log cap: each application logs under its own private/logs/, each file at most 256 KB
// The members of a bundle (neoaprs/cli/supportreadme.py FILE_HELP): the files it holds by name, the
// logs, and the `.error.txt` of a part that could not be made.
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

/**
 * Where the files are kept: private/support/ beside this folder, which Apache refuses to serve; one
 * more .htaccess is written in it.
 */
function support_dir(): string
{
    $dir = getenv('SUPPORT_DIR') ?: dirname(__DIR__) . '/private/support';
    if (!is_dir($dir) && !@mkdir($dir, 0700, true) && !is_dir($dir)) support_refuse(500, 'storage');
    if (!is_file("$dir/.htaccess")) @file_put_contents("$dir/.htaccess", "Require all denied\n");
    return $dir;
}

/**
 * A line in private/logs/support.log beside the folder of the files; the older half goes past 256
 * KB. No address or note is written.
 */
function support_log(string $dir, string $line): void
{
    $folder = dirname($dir) . '/logs';
    if (!is_dir($folder) && !@mkdir($folder, 0700, true) && !is_dir($folder)) return;
    $path = "$folder/support.log";
    if (is_file($path) && filesize($path) > LOG_MAX_BYTES) @file_put_contents($path, substr((string) file_get_contents($path), (int) (LOG_MAX_BYTES / 2)), LOCK_EX);
    @file_put_contents($path, gmdate('Y-m-d\TH:i:s\Z') . "  $line\n", FILE_APPEND | LOCK_EX);
}

/**
 * The address as it is hashed: an IPv6 address by its first 64 bits (the rest is the household's to
 * choose).
 */
function support_address(): string
{
    $ip = (string) ($_SERVER['REMOTE_ADDR'] ?? '');
    $raw = @inet_pton($ip);
    if ($raw === false) return $ip;
    return strlen($raw) === 16 ? substr($raw, 0, 8) : $raw;
}

/** The hash of the address under the salt of the folder. */
function support_key(string $dir, string $address): string
{
    $saltFile = "$dir/salt";
    if (!is_file($saltFile)) @file_put_contents($saltFile, bin2hex(random_bytes(16)), LOCK_EX);
    return substr(hash('sha256', trim((string) @file_get_contents($saltFile)) . '|' . $address), 0, 16);
}

/**
 * The counts of the last hour in rate.json, {"stored": {HASH: [times]}, "bad": {HASH: [times]}}: `$use` gets them with
 * the hour's old times dropped and returns the counts to keep (null: unchanged, but dropped times are written back), under one lock.
 * Only hashes are kept, and only for the hour.
 *
 * @param callable(array<string, array<string, list<int>>>): ?array<string, array<string, list<int>>> $use
 */
function support_counts(string $dir, int $now, callable $use): void
{
    $h = @fopen("$dir/rate.json", 'c+');
    if ($h === false) support_refuse(500, 'storage');
    flock($h, LOCK_EX);
    $seen = json_decode((string) stream_get_contents($h), true);
    $seen = is_array($seen) ? $seen : [];
    $counts = ['stored' => [], 'bad' => []];
    $dropped = false;
    foreach (array_keys($counts) as $kind) {
        foreach (is_array($seen[$kind] ?? null) ? $seen[$kind] : [] as $k => $times) {
            if (!is_array($times)) {
                $dropped = true;
                continue;
            }
            $kept = array_values(array_filter($times, fn($t) => is_int($t) && $t > $now - RATE_WINDOW_SEC));
            if (count($kept) !== count($times)) $dropped = true;
            if ($kept) $counts[$kind][(string) $k] = $kept;
        }
    }
    $changed = $use($counts);
    if ($changed === null && $dropped) $changed = $counts;  // a read-only use still forgets what has expired
    if ($changed !== null) {
        $changed['bad'] = array_slice($changed['bad'], -BAD_KEYS_MAX, null, true);
        ftruncate($h, 0);
        rewind($h);
        fwrite($h, json_encode($changed));
    }
    flock($h, LOCK_UN);
    fclose($h);
}

/**
 * Whether the address may still send requests that are refused (20 an hour); asking counts nothing.
 */
function support_bad_allowed(string $dir, string $key, int $now): bool
{
    $ok = true;
    support_counts($dir, $now, function (array $counts) use ($key, &$ok): ?array {
        $ok = count($counts['bad'][$key] ?? []) < BAD_PER_ADDRESS;
        return null;
    });
    return $ok;
}

/** A refused request, counted against its address only. */
function support_bad_count(string $dir, string $key, int $now): void
{
    support_counts($dir, $now, function (array $counts) use ($key, $now): array {
        $counts['bad'][$key][] = $now;
        return $counts;
    });
}

/**
 * Count a file about to be stored against the address and the whole; false, nothing counted, when
 * either has used its hour's share.
 */
function support_allowed(string $dir, string $key, int $now): bool
{
    $ok = false;
    support_counts($dir, $now, function (array $counts) use ($key, $now, &$ok): ?array {
        $all = 0;
        foreach ($counts['stored'] as $times) $all += count($times);
        $ok = count($counts['stored'][$key] ?? []) < RATE_PER_ADDRESS && $all < RATE_IN_ALL;
        if (!$ok) return null;
        $counts['stored'][$key][] = $now;
        return $counts;
    });
    return $ok;
}

/**
 * The lock held from counting the folder to storing the file, so simultaneous uploads do not all
 * see the room one takes; released when the request ends.
 */
function support_store_lock(string $dir): mixed
{
    $h = @fopen("$dir/store.lock", 'c');
    if ($h === false) support_refuse(500, 'storage');
    flock($h, LOCK_EX);
    return $h;
}

/**
 * Remove stored files older than 30 days; return {bytes, kept} of what remains (kept: references,
 * one json each). Only reference-shaped files are touched.
 */
function support_tidy(string $dir, int $now): array
{
    $bytes = 0;
    $kept = 0;
    foreach (@scandir($dir) ?: [] as $name) {
        if (!preg_match('~^NEO-\d{8}-\d{4}-[0-9A-F]+\.(zip|json|json\.part)$~', $name)) continue;
        $path = "$dir/$name";
        $time = @filemtime($path);
        if ($time !== false && $time < $now - KEEP_DAYS * 86400) {
            @unlink($path);
            continue;
        }
        $bytes += (int) @filesize($path);
        if (str_ends_with($name, '.json')) $kept++;
    }
    return ['bytes' => $bytes, 'kept' => $kept];
}

/**
 * One mail to the project when the folder first has no room (full.flag records it; removed when a
 * file is stored again): filling it switches the logs off for the month.
 */
function support_full_notice(string $dir, int $now): void
{
    if (is_file("$dir/full.flag")) return;
    @file_put_contents("$dir/full.flag", gmdate('Y-m-d\TH:i:s\Z', $now) . "\n");
    try {
        $mailed = support_send_mail('NeoAPRS logs: the folder is full', "The folder of the sent logs is full (" . FOLDER_MAX_FILES . " references or " . intdiv(FOLDER_MAX_BYTES, 1048576) . " MB), and new ones are refused until older ones are fetched and removed or are 30 days old.\n\nserver/support-fetch.sh brings them.\n");
    } catch (Throwable $e) {
        $mailed = false;
    }
    if (!$mailed) support_log($dir, 'the mail that the folder is full was not sent');
}

/**
 * The member names of the zip at `path` from its central directory (no zip extension needed); null
 * when it is no zip of ours or unpacks to more than MAX_UNPACKED.
 */
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
    $unpacked = 0;
    $at = 0;
    while (count($names) < $count) {
        if (substr($dir, $at, 4) !== "PK\x01\x02" || strlen($dir) < $at + 46) return null;
        $unpacked += unpack('V', substr($dir, $at + 24, 4))[1];
        if ($unpacked > MAX_UNPACKED) return null;
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

/**
 * True when the members look like a NeoAPRS bundle: summary.txt and only the names a bundle has.
 */
function support_is_bundle(array $names): bool
{
    if (!in_array('summary.txt', $names, true)) return false;
    foreach ($names as $name) {
        if (!preg_match(MEMBER_NAME, $name)) return false;
    }
    return true;
}

/**
 * A word of the form: only the characters in `$keep`, at most `$max` of them. Every set this script keeps has no line end
 * or control character, so the result may stand in the mail's subject: Psalm is told so here, since it cannot follow a pattern.
 *
 * @psalm-taint-escape header
 */
function support_clean(mixed $value, string $keep, int $max): string
{
    return is_string($value) ? substr((string) preg_replace('/[^' . $keep . ']/', '', $value), 0, $max) : '';
}

/**
 * The note: invalid UTF-8 and control characters other than line break and tab are dropped, line
 * breaks are \n, cut to 2000 characters.
 */
function support_note(mixed $value): string
{
    if (!is_string($value)) return '';
    $text = str_replace(["\r\n", "\r"], "\n", $value);
    $clean = preg_replace('/[^\x{0009}\x{000A}\x{0020}-\x{007E}\x{00A0}-\x{10FFFF}]/u', '', $text);
    if ($clean === null) $clean = (string) preg_replace('/[^\x09\x0A\x20-\x7E]/', '', $text);  // not UTF-8 at all: its ASCII is kept
    $chars = preg_split('//u', $clean, MAX_NOTE + 1, PREG_SPLIT_NO_EMPTY);
    return trim(implode('', array_slice($chars === false ? [] : $chars, 0, MAX_NOTE)));
}

/**
 * The address for a reply: one "@" with something on each side, no blank or control character, at
 * most 254 characters; anything else, invalid UTF-8 too, is ''.
 */
function support_email(mixed $value): string
{
    if (!is_string($value) || $value === '' || strlen($value) > 4 * MAX_EMAIL) return '';
    if (preg_match('/[\x{0000}-\x{0020}\x{007F}-\x{00A0}\x{1680}\x{2000}-\x{200A}\x{2028}\x{2029}\x{202F}\x{205F}\x{3000}\x{FEFF}]/u', $value) !== 0) return '';
    if (preg_match_all('/./su', $value) > MAX_EMAIL) return '';
    $parts = explode('@', $value);
    return count($parts) === 2 && $parts[0] !== '' && $parts[1] !== '' ? $value : '';
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
    /**
     * The one plain mail to the project, as the status application sends its alerts. Headers and
     * subject are ours; what a person wrote is in the body only.
     */
    function support_send_mail(string $subject, string $body, string $replyTo = ''): bool
    {
        if (preg_match('/[\r\n]/', $subject)) return false;
        return @mail(SUPPORT_TO, $subject, $body, support_mail_headers($replyTo));
    }
}

/** The mail's headers; a reply goes to the person's address when it is a plain one, else to nobody's. */
function support_mail_headers(string $replyTo): string
{
    $reply = support_reply_to($replyTo);
    return 'From: ' . SUPPORT_FROM . "\r\n" . ($reply !== '' ? "Reply-To: $reply\r\n" : '')
         . "Content-Type: text/plain; charset=utf-8\r\nX-Mailer: neoaprs-support\r\n";
}

/** The address as a header may carry it: plain ASCII, a name, "@" and a dotted host; anything else is ''. */
function support_reply_to(string $email): string
{
    return preg_match('/^[A-Za-z0-9.!#$%&\'*+\/=?^_`{|}~-]{1,64}@[A-Za-z0-9-]{1,63}(\.[A-Za-z0-9-]{1,63})+$/D', $email) === 1 ? $email : '';
}

function support_receive(): never
{
    if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') support_refuse(405, 'method', ['Allow: POST']);
    $length = (int) ($_SERVER['CONTENT_LENGTH'] ?? 0);
    $postMax = ini_parse_quantity((string) ini_get('post_max_size'));
    if ($length > MAX_BODY || ($postMax > 0 && $length > $postMax)) support_refuse(413, 'too_large');

    $now = time();
    $dir = support_dir();
    $key = support_key($dir, support_address());
    if (!support_bad_allowed($dir, $key, $now)) support_refuse(429, 'rate', ['Retry-After: ' . RATE_WINDOW_SEC]);

    $file = $_FILES['bundle'] ?? null;
    $note = support_note($_POST['note'] ?? '');
    $form = strtolower(trim(explode(';', (string) ($_SERVER['CONTENT_TYPE'] ?? ''))[0])) === 'multipart/form-data';  // the program posts a form: a note in any other body is refused
    $alone = $form && $_FILES === [] && !array_key_exists('bundle', $_POST);  // no file in the form: the note alone, which must have words
    $names = null;
    $size = 0;
    if ($alone) {
        $refusal = $note === '' ? [400, 'bad_request'] : null;
    } elseif (!is_array($file) || !is_string($file['tmp_name'] ?? null)) {
        $refusal = [400, 'bad_request'];
    } elseif (in_array($file['error'], [UPLOAD_ERR_INI_SIZE, UPLOAD_ERR_FORM_SIZE], true)) {
        $refusal = [413, 'too_large'];
    } elseif ($file['error'] !== UPLOAD_ERR_OK || !is_uploaded_file($file['tmp_name'])) {
        $refusal = [400, 'bad_request'];
    } elseif (($size = (int) filesize($file['tmp_name'])) > MAX_FILE) {
        $refusal = [413, 'too_large'];
    } elseif (($names = support_members($file['tmp_name'])) === null || !support_is_bundle($names)) {
        $refusal = [400, 'not_a_bundle'];
    } else {
        $refusal = null;
    }
    if ($refusal !== null) {
        support_bad_count($dir, $key, $now);
        support_refuse($refusal[0], $refusal[1]);
    }

    $lock = support_store_lock($dir);
    $held = support_tidy($dir, $now);
    if ($held['kept'] >= FOLDER_MAX_FILES || $held['bytes'] + $size > FOLDER_MAX_BYTES) {
        support_log($dir, 'the folder is full (' . $held['kept'] . ' kept, ' . intdiv($held['bytes'], 1024) . ' KB): a ' . ($alone ? 'note' : 'file') . ' was refused');
        support_full_notice($dir, $now);
        support_refuse(429, 'rate', ['Retry-After: ' . RATE_WINDOW_SEC]);
    }
    if (is_file("$dir/full.flag")) @unlink("$dir/full.flag");
    if (!support_allowed($dir, $key, $now)) support_refuse(429, 'rate', ['Retry-After: ' . RATE_WINDOW_SEC]);

    $call     = support_clean($_POST['call'] ?? '', 'A-Za-z0-9-', 12);
    $version  = support_clean($_POST['version'] ?? '', '0-9A-Za-z._+-', 20);
    $platform = support_clean($_POST['platform'] ?? '', '0-9A-Za-z._-', 40);
    $email    = support_email($_POST['email'] ?? '');

    $ref = support_reference($dir, $now);
    if (!$alone) {
        if (!@move_uploaded_file($file['tmp_name'], "$dir/$ref.zip")) support_refuse(500, 'storage');
        @chmod("$dir/$ref.zip", 0600);
    }
    $meta = ['ref' => $ref, 'time' => gmdate('Y-m-d\TH:i:s\Z', $now), 'call' => $call, 'email' => $email, 'version' => $version, 'platform' => $platform, 'file' => !$alone, 'size' => $size, 'note' => $note];
    $json = json_encode($meta, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT | JSON_INVALID_UTF8_SUBSTITUTE);
    if ($json === false || @file_put_contents("$dir/$ref.json.part", $json . "\n") === false || !@rename("$dir/$ref.json.part", "$dir/$ref.json")) {
        if (!$alone) @unlink("$dir/$ref.zip");
        support_refuse(500, 'storage');
    }
    @chmod("$dir/$ref.json", 0600);
    flock($lock, LOCK_UN);
    fclose($lock);

    $subject = ($alone ? 'NeoAPRS message ' : 'NeoAPRS logs ') . $ref . ($call !== '' ? ' from ' . $call : '');
    $body = ($alone ? "A NeoAPRS message was sent, without the support file.\n\n" : "A NeoAPRS support file was sent.\n\n")
          . "Reference: $ref\nCall:      " . ($call ?: '-') . "\nEmail:     " . ($email ?: '-') . "\nVersion:   " . ($version ?: '-') . "\nPlatform:  " . ($platform ?: '-') . "\n"
          . ($alone ? '' : 'Size:      ' . max(1, intdiv($size, 1024)) . " KB\n") . 'Time:      ' . gmdate('Y-m-d H:i', $now) . " UTC\n\n"
          . "Note:\n" . ($note !== '' ? $note : '(none)') . "\n"
          . ($alone ? '' : "\nThe file is on the server; server/support-fetch.sh brings it.\n");
    try {
        $mailed = support_send_mail($subject, $body, $email);
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
