// What the page tells a person about the secure connection (https): the hover text of its switch, the address of the secure page, where the daemon gives the certificate of NeoAPRS's own certificate authority, and the few steps to
// make a device trust it, for the device this is. The steps are of the systems' own menus and only the person can walk them: a page can install nothing. Without the certificate the browser shows a warning the first time,
// which can also be continued past.

/** The text of the (i) beside the switch. */
export const HTTPS_TIP =
  "Needed for pop-ups on phones and for installing NeoAPRS as an app. Browsers show a warning the first time; you can continue past it, or install NeoAPRS's certificate on each device to make the warning go away.";

/** Where the daemon gives the authority's certificate, and the name the download has. */
export const CERT_PATH = "/neoaprs-ca.crt";
export const CERT_FILE = "NeoAPRS-CA.crt";

export type Device = "android" | "ios" | "windows" | "mac" | "linux" | "firefox";

export const DEVICES: readonly { value: Device; label: string }[] = [
  { value: "android", label: "Android" },
  { value: "ios", label: "iPhone, iPad" },
  { value: "windows", label: "Windows" },
  { value: "mac", label: "macOS" },
  { value: "linux", label: "Linux (Chrome)" },
  { value: "firefox", label: "Firefox" },
];

/** Which device the steps are for, from the user agent: a phone or tablet by its system (Firefox there uses the system's list), a computer by its system, but Firefox on a computer has a list of its own. An iPad asks for the desktop
 * site and says Macintosh; it has a touch screen. */
export function deviceOf(userAgent: string, touchPoints = 0): Device {
  if (/Android/i.test(userAgent)) return "android";
  if (/iPhone|iPad|iPod/i.test(userAgent) || (/Macintosh/.test(userAgent) && touchPoints > 1)) return "ios";
  if (/Firefox\//.test(userAgent)) return "firefox";
  if (/Windows/.test(userAgent)) return "windows";
  if (/Macintosh|Mac OS X/.test(userAgent)) return "mac";
  return "linux";
}

const FILE = `NeoAPRS-CA.crt`;

/** The steps after the download, for each device. */
export const STEPS: Readonly<Record<Device, readonly string[]>> = {
  android: [
    'Open Settings → Security → Encryption & credentials → Install a certificate → CA certificate (or search the settings for "CA certificate").',
    `Tap "Install anyway" and choose ${FILE} from Downloads.`,
    "Open the secure page again.",
  ],
  ios: [
    "Open this page in Safari, tap Download certificate and Allow.",
    "Open Settings → Profile Downloaded → Install.",
    'Open Settings → General → About → Certificate Trust Settings and switch on "NeoAPRS local CA".',
  ],
  windows: [
    `Open ${FILE} → Install Certificate → Current User or Local Machine → Next.`,
    'Choose "Place all certificates in the following store" → Browse → Trusted Root Certification Authorities → Next → Finish.',
    "Restart the browser.",
  ],
  mac: [
    `Open Keychain Access and import ${FILE} into the System keychain (File → Import Items).`,
    'Double-click "NeoAPRS local CA", open Trust and choose Always Trust.',
    "Restart the browser.",
  ],
  linux: [
    "Open Settings → Privacy and security → Security → Manage certificates → Authorities.",
    `Click Import, choose ${FILE} and tick "Trust this certificate for identifying websites".`,
    "Restart the browser.",
  ],
  firefox: [
    "Open Settings → Privacy & Security → Certificates → View Certificates → Authorities.",
    `Click Import, choose ${FILE} and tick "Trust this CA to identify websites".`,
  ],
};

/** The secure page on the host the page was opened at (an IPv6 address already has its brackets in `location.hostname`). */
export const secureUrl = (port: number, hostname: string = location.hostname): string => `https://${hostname}:${port}/`;
