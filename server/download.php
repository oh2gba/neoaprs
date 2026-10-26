<?php
// The download buttons of the project page. A release file carries its version in its name
// (NeoAPRS-Setup-0.9.1.exe), so GitHub's releases/latest/download/NAME cannot name it; this page does:
//   download.php?f=windows | appimage | deb-amd64 | deb-arm64 | wheel
// answers 302 to that file of the latest release (the version comes from latest.php, as version.php has
// it). An unknown f, or no known version yet, goes to the release page of the latest release.
//
// Each call is appended to a monthly log file in log/ (not web-readable, see log/.htaccess) as time, f
// and the version only. No IP address or anything else about the caller is kept.

header('Cache-Control: no-store');

require __DIR__ . '/latest.php';

const RELEASES_PAGE = 'https://github.com/oh2gba/neoaprs/releases/latest';
const DOWNLOAD_BASE = 'https://github.com/oh2gba/neoaprs/releases/download/v';

$names = [
    'windows'    => 'NeoAPRS-Setup-%s.exe',
    'appimage'   => 'NeoAPRS-%s-x86_64.AppImage',
    'deb-amd64'  => 'neoaprs_%s_amd64.deb',
    'deb-arm64'  => 'neoaprs_%s_arm64.deb',
    'wheel'      => 'neoaprs-%s-py3-none-any.whl',
];

$f = is_string($_GET['f'] ?? null) ? $_GET['f'] : '';
$version = isset($names[$f]) ? neoaprs_latest_version() : '';
$target = $version !== '' ? DOWNLOAD_BASE . "$version/" . sprintf($names[$f], $version) : RELEASES_PAGE;

$shown = substr(preg_replace('/[^0-9A-Za-z._-]/', '', $f), 0, 20);
$line = gmdate('Y-m-d\TH:i') . "Z\t" . ($shown ?: '-') . "\t" . ($version ?: '-') . "\n";
@file_put_contents(__DIR__ . '/log/downloads-' . gmdate('Y-m') . '.log', $line, FILE_APPEND | LOCK_EX);

header('Location: ' . $target, true, 302);
