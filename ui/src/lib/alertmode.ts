// What this browser does for a message to us (Settings, Notifications, "In this browser"), kept as
// one choice: nothing, the chime, the chime and a notification, or a notification only. A
// notification is the browser's own.
import { t } from "@/i18n";
import { readStored, removeStored, writeStored } from "@/lib/storage";

export type AlertMode = "off" | "sound" | "both" | "popup";

export const MODE_KEY = "alert.mode";

const MODES: readonly AlertMode[] = ["off", "sound", "both", "popup"];

/** The choice that has these parts: Alert is ticked, so neither part is the sound. */
export const modeOf = (sound: boolean, popup: boolean): AlertMode => (sound && popup ? "both" : popup ? "popup" : "sound");

export const wantsSound = (mode: AlertMode): boolean => mode === "sound" || mode === "both";
export const wantsPopup = (mode: AlertMode): boolean => mode === "both" || mode === "popup";

/**
 * The choice without its notification, for a page that cannot show one: sound and notification
 * becomes sound, notification only becomes off.
 */
export const withoutPopup = (mode: AlertMode): AlertMode => (wantsPopup(mode) ? (wantsSound(mode) ? "sound" : "off") : mode);

/**
 * Why this browser cannot show a notification, else undefined: `possible` is a secure context with
 * the API, `permission` the browser's answer so far.
 */
export function popupWhy(possible: boolean, permission: NotificationPermission): string | undefined {
  if (!possible) return t("settings.alert_mode.why_off");
  return permission === "denied" ? t("settings.alert_mode.why_blocked") : undefined;
}

/**
 * The default: off on the machine the daemon runs on (its own alert notifies there), elsewhere
 * sound and a notification where allowed, else sound. The Mac app window (`noPopup`) starts at
 * sound even on that machine, since the daemon's command has nothing to run there.
 */
export function defaultMode(here: boolean, why: string | undefined, noPopup = false): AlertMode {
  if (noPopup) return "sound";
  return here ? "off" : why === undefined ? "both" : "sound";
}

const OLD_KEYS = ["alert.web", "alert.sound", "alert.notify"] as const;

/**
 * The choice from the three older switches (web alert, Sound, Notifications; a missing one had its
 * default), or null if none was ever stored.
 */
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

/**
 * The mode this browser kept; else the one its older switches make (stored under the new key, the
 * old ones removed); else the default. A notification this address cannot show is dropped from a
 * migrated choice, and from any choice where the page can show none (`noPopup`: the desktop app's
 * window).
 */
export function storedMode(here: boolean, why: string | undefined, noPopup = false): AlertMode {
  const mode = keptMode(here, why, noPopup);
  return noPopup ? withoutPopup(mode) : mode;
}

function keptMode(here: boolean, why: string | undefined, noPopup: boolean): AlertMode {
  const stored = readStored(MODE_KEY);
  const found = MODES.find((m) => m === stored);
  if (found) return found;
  const old = fromSwitches(here);
  if (old === null) return defaultMode(here, why, noPopup);
  const mode = why !== undefined ? withoutPopup(old) : old;
  writeStored(MODE_KEY, mode);
  OLD_KEYS.forEach(removeStored);
  return mode;
}
