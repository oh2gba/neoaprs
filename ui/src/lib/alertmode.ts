// What this browser does for a message to us, as one choice (the Settings tab, "Notifications", "In this browser"): nothing, the chime, the chime and a pop-up, or a pop-up only. A pop-up is a notification of the browser.
import { t } from "@/i18n";
import { lazyText } from "@/lib/lazytext";
import { readStored, removeStored, writeStored } from "@/lib/storage";

export type AlertMode = "off" | "sound" | "both" | "popup";

export const MODE_KEY = "alert.mode";

export const MODES: readonly { value: AlertMode; readonly label: string }[] = [
  lazyText({ value: "off" as const }, { label: () => t("settings.alert_mode.off") }),
  lazyText({ value: "sound" as const }, { label: () => t("settings.alert_mode.sound") }),
  lazyText({ value: "both" as const }, { label: () => t("settings.alert_mode.both") }),
  lazyText({ value: "popup" as const }, { label: () => t("settings.alert_mode.popup") }),
];

export const wantsSound = (mode: AlertMode): boolean => mode === "sound" || mode === "both";
export const wantsPopup = (mode: AlertMode): boolean => mode === "both" || mode === "popup";

/** Why this browser cannot show a pop-up, else undefined: `possible` is a secure context with the API, `permission` what the browser has answered so far. */
export function popupWhy(possible: boolean, permission: NotificationPermission): string | undefined {
  if (!possible) return t("settings.alert_mode.why_off");
  return permission === "denied" ? t("settings.alert_mode.why_blocked") : undefined;
}

/** The default for a page opened on the machine the daemon runs on (where the daemon's own alert notifies) is off, elsewhere the sound and a pop-up where one is allowed, else the sound. */
export function defaultMode(here: boolean, why: string | undefined): AlertMode {
  return here ? "off" : why === undefined ? "both" : "sound";
}

const OLD_KEYS = ["alert.web", "alert.sound", "alert.notify"] as const;

/** The choice of the three switches an earlier page kept (the web alert, Sound, Notifications; a missing one had its default), or null when none of them was ever stored. */
function fromSwitches(here: boolean): AlertMode | null {
  const web = readStored("alert.web");
  const sound = readStored("alert.sound");
  const notify = readStored("alert.notify");
  if (web === null && sound === null && notify === null) return null;
  if (!(web === "on" || (web === null && !here))) return "off";
  const chime = sound !== "off";
  const popup = notify !== "off";
  return chime ? (popup ? "both" : "sound") : popup ? "popup" : "off";
}

/** The mode this browser kept; else the one its older switches make (kept under the new key, the old ones removed, so nobody's choice is lost); else the default. A pop-up that this address cannot show is dropped from a migrated choice. */
export function storedMode(here: boolean, why: string | undefined): AlertMode {
  const stored = readStored(MODE_KEY);
  const found = MODES.find((m) => m.value === stored);
  if (found) return found.value;
  const old = fromSwitches(here);
  if (old === null) return defaultMode(here, why);
  const mode = why !== undefined && wantsPopup(old) ? (wantsSound(old) ? "sound" : "off") : old;
  writeStored(MODE_KEY, mode);
  OLD_KEYS.forEach(removeStored);
  return mode;
}
