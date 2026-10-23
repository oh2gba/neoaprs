// What the page tells a person who opened it over plain http (the Raspberry Pi's address) and wants pop-ups: which browser this is, and the few things to type into it. A browser shows pop-ups only for https, localhost or an address
// it was told to trust, and only the person can tell it (Firefox in about:config, Chrome and its relatives in chrome://flags): a page can neither open those pages nor change them.

export type BrowserKind = "firefox" | "chrome" | "edge" | "brave" | "opera" | "phone" | "other";
export type ChromiumKind = "chrome" | "edge" | "brave" | "opera";

/** The name shown to the person and the scheme the flags page has, for each Chromium-based browser. */
export const CHROMIUM: Readonly<Record<ChromiumKind, { name: string; scheme: string }>> = {
  chrome: { name: "Chrome", scheme: "chrome" },
  edge: { name: "Edge", scheme: "edge" },
  brave: { name: "Brave", scheme: "brave" },
  opera: { name: "Opera", scheme: "opera" },
};

export const isChromium = (kind: BrowserKind): kind is ChromiumKind => kind in CHROMIUM;

/** Which browser this is, from its user agent (`brave` is true when the browser says so: its user agent is Chrome's). A phone or tablet is one kind whatever the browser, as none of them has the settings below. */
export function browserKind(userAgent: string, brave = false): BrowserKind {
  if (/Android|iPhone|iPad|iPod|Mobile/i.test(userAgent)) return "phone";
  if (/Firefox\//.test(userAgent)) return "firefox";
  if (/Edg\//.test(userAgent)) return "edge";
  if (/OPR\//.test(userAgent)) return "opera";
  if (brave) return "brave";
  if (/Chrome\//.test(userAgent)) return "chrome";
  return "other";
}

/** The address a person pastes in the address bar for the flag. */
export const flagAddress = (scheme: string): string => `${scheme}://flags/#unsafely-treat-insecure-origin-as-secure`;

/** Firefox as a Flatpak (KDE) hands its pop-ups to a portal that may hide them: the two commands that let it use the notification service itself. */
export const FLATPAK_COMMANDS: readonly string[] = [
  "flatpak override --user --talk-name=org.freedesktop.Notifications org.mozilla.firefox",
  "flatpak override --user --env=NOTIFY_IGNORE_PORTAL=1 org.mozilla.firefox",
];

/** True for a Linux desktop, where Firefox may be a Flatpak. */
export const onLinuxDesktop = (userAgent: string): boolean => /Linux|X11/.test(userAgent) && !/Android/.test(userAgent);
