// What this browser does for a message to us (the Settings tab, "Notifications", "In this browser": a Notify me tickbox and the tickboxes Sound and Notification), kept as one choice: nothing, the chime, the chime and a notification, or a notification only, so that what an earlier page kept still reads. A notification is a notification of the browser.
import { t } from "@/i18n";
import { readStored, removeStored, writeStored } from "@/lib/storage";

export type AlertMode = "off" | "sound" | "both" | "popup";

export const MODE_KEY = "alert.mode";

const MODES: readonly AlertMode[] = ["off", "sound", "both", "popup"];

/** The choice that has these parts: Alert is ticked, so neither part is the sound. */
export const modeOf = (sound: boolean, popup: boolean): AlertMode => (sound && popup ? "both" : popup ? "popup" : "sound");

export const wantsSound = (mode: AlertMode): boolean => mode === "sound" || mode === "both";
export const wantsPopup = (mode: AlertMode): boolean => mode === "both" || mode === "popup";

/** The choice with its notification taken out, for a page that cannot show one: sound and notification is the sound, notification only is off. */
export const withoutPopup = (mode: AlertMode): AlertMode => (wantsPopup(mode) ? (wantsSound(mode) ? "sound" : "off") : mode);

/** Why this browser cannot show a notification, else undefined: `possible` is a secure context with the API, `permission` what the browser has answered so far. */
export function popupWhy(possible: boolean, permission: NotificationPermission): string | undefined {
  if (!possible) return t("settings.alert_mode.why_off");
  return permission === "denied" ? t("settings.alert_mode.why_blocked") : undefined;
}

/** The default for a page opened on the machine the daemon runs on (where the daemon's own alert notifies) is off, elsewhere the sound and a notification where one is allowed, else the sound. The app's window on a Mac (`noPopup`) is the exception on the machine itself: its daemon's command has nothing to run there, so the window starts at the sound. */
export function defaultMode(here: boolean, why: string | undefined, noPopup = false): AlertMode {
  if (noPopup) return "sound";
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

/** The mode this browser kept; else the one its older switches make (kept under the new key, the old ones removed, so nobody's choice is lost); else the default. A notification that this address cannot show is dropped from a migrated choice,
 *  and from any choice where the page can show none at all (`noPopup`: the desktop app's own window). */
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
