// What the page tells a person about the secure connection (https): the hover text of its switch, the address of the secure page, where the daemon gives the certificate of NeoAPRS's own certificate authority, and the few steps to
// make a device trust it, for the device this is. The steps are of the systems' own menus and only the person can walk them: a page can install nothing. Without the certificate the browser shows a warning the first time,
// which can also be continued past.
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import type { HttpsState } from "@/protocol/protocol";

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

const file = { file: CERT_FILE };

/** The steps after the download, for each device, in the language of the page (the menus are the systems' own, in their words: a language gives the steps as its systems write them). They are made when read, so `STEPS.android` follows the language. */
export const STEPS: Readonly<Record<Device, readonly string[]>> = {
  get android() {
    return [t("help.cert.android1"), t("help.cert.android2", file), t("help.cert.android3")];
  },
  get ios() {
    return [t("help.cert.ios1"), t("help.cert.ios2"), t("help.cert.ios3")];
  },
  get windows() {
    return [t("help.cert.windows1", file), t("help.cert.windows2"), t("help.cert.windows3")];
  },
  get mac() {
    return [t("help.cert.mac1", file), t("help.cert.mac2"), t("help.cert.mac3")];
  },
  get linux() {
    return [t("help.cert.linux1"), t("help.cert.linux2", file), t("help.cert.linux3")];
  },
  get firefox() {
    return [t("help.cert.firefox1"), t("help.cert.firefox2", file)];
  },
};

/** The secure page on the host the page was opened at (an IPv6 address already has its brackets in `location.hostname`). */
export const secureUrl = (port: number, hostname: string = location.hostname): string => `https://${hostname}:${port}/`;

/** Why the secure connection could not start, in words, by the daemon's code of it (`HttpsState.reason`); "" for none. */
const REASONS: Record<Exclude<HttpsState["reason"], "">, MessageId> = {
  no_library: "settings.https.reason.no_library",
  clock: "settings.https.reason.clock",
  certificates: "settings.https.reason.certificates",
  no_port: "settings.https.reason.no_port",
};
export function reasonText(reason: HttpsState["reason"]): string {
  const id = REASONS[reason as Exclude<HttpsState["reason"], "">] as MessageId | undefined; // (none for "" and for a code of a daemon of another build)
  return id === undefined ? "" : t(id);
}
