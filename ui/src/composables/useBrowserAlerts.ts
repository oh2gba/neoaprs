// The alert of this browser for a message to us and for an alert set on a station (which says what happened and is no message: its own notification title, a bell in the browser tab), and its one choice (the Settings tab, "Notifications", "In this browser"; kept in localStorage, so each device decides): off, sound, sound and notification, or notification only. It is off by
// default on the machine the daemon runs on (the page on the loopback, the desktop app: the daemon's own alert command notifies there, except on a Mac, where the window starts at the sound), and elsewhere sound and notification where the browser can show one, else sound. The sound is
// the chime (the first click or key press unlocks the audio); a notification is one of the browser, shown where it allows one (a secure context, permission given), and where none is shown, or the browser fails to show it, the
// browser tab alerts (useTabAlert). The permission is asked only in a click: on choosing a notification, and on the Test notification button. Test sound and Test notification each say, for a few seconds, what happened.
// In the desktop app's own window there is no notification: nothing in the app answers a page that asks for one (Qt's window leaves the question unanswered, pywebview's WebView2 has no handler for it). Where the daemon's own alert
// tells (Linux and Windows, `daemonAlone`: its command shows the notification and plays the sound on that same computer) the window's alert does nothing, and a choice it kept before stays in the browser's memory unread; on a Mac the window's
// alert is the chime alone, a kept choice with a notification is read without it, and the permission is never asked.
import { computed, onScopeDispose, getCurrentScope, ref, type Ref } from "vue";
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import { useTabAlert } from "@/composables/useTabAlert";
import { Chime } from "@/lib/chime";
import { storedMode, popupWhy, wantsPopup, wantsSound, MODE_KEY, type AlertMode } from "@/lib/alertmode";
import { isLoopbackHost, notificationTitle } from "@/lib/pagealert";
import { daemonTells, inApp } from "@/lib/shell";
import { writeStored } from "@/lib/storage";
import { firedText } from "@/lib/stationalert";
import type { MessageRow, StationAlertMessage } from "@/protocol/protocol";

/** What an alert needs of a message. */
export type Alerted = Pick<MessageRow, "id" | "from_call" | "text">;

/** The message of the Test notification, in the language of the page. */
const testMessage = (): Alerted => ({ id: 0, from_call: "NEOAPRS", text: t("settings.alert.test_message") });
/** After a long disconnect many messages can arrive at once: so many notifications, the rest are in the page. */
const POPUPS_MAX = 5;
const STATUS_MS = 5000;

/** The words after a Test button, which go after a few seconds (the id of the words is kept, so that they follow the language of the page). */
function useStatus() {
  const said = ref<MessageId | "">("");
  const text = computed(() => (said.value === "" ? "" : t(said.value)));
  let timer: ReturnType<typeof setTimeout> | undefined;
  const set = (words: MessageId): void => {
    said.value = words;
    clearTimeout(timer);
    timer = setTimeout(() => (said.value = ""), STATUS_MS);
  };
  if (getCurrentScope()) onScopeDispose(() => clearTimeout(timer));
  return { text, set };
}

/** Shows a notification of the browser; false when the browser refuses (some, on a phone, want a service worker), and `failed` is called when it could not show it after all. A click focuses the page and does `then`. A notification
 *  with the tag of one still on show replaces it without a sound. */
function notify(title: string, body: string, tag: string, then: () => void, failed: () => void): boolean {
  try {
    const popup = new Notification(title, { body, tag });
    popup.onerror = failed;
    popup.onclick = () => {
      window.focus();
      popup.close();
      then();
    };
    return true;
  } catch {
    return false;
  }
}

/** The notification of a message: a click on it opens the conversation for a real message (`open` is given). A test has a tag of its own each time. */
function showPopup(message: Alerted, open: ((call: string) => void) | null, failed: () => void): boolean {
  const tag = open !== null ? `neoaprs-${message.id}` : `neoaprs-test-${Date.now()}`;
  return notify(notificationTitle(message.from_call), message.text, tag, () => open?.(message.from_call), failed);
}

/** The notification of an alert set on a station ("APRS alert: OH2XYZ", "OH2XYZ is on the air"): its own title, so that it does not look like a message; a click brings the page to the front. */
function showStationPopup(fired: StationAlertMessage, failed: () => void): boolean {
  const tag = `neoaprs-alert-${fired.call}-${fired.kind}-${fired.at}`;
  return notify(t("station.alert.popup_title", { call: fired.call }), firedText(fired), tag, () => undefined, failed);
}

/** What the browser lets the page do with notifications at this moment; denied where it cannot show one. */
function permissionNow(possible: boolean): NotificationPermission {
  return possible ? Notification.permission : "denied";
}

/** The first click or key press in the page unlocks the audio (a browser lets a page make sound only after one); the listeners go once it has worked. */
function useAudioUnlock(chime: Chime): void {
  function unlock(): void {
    void chime.unlock().then((ok) => {
      if (ok) remove();
    });
  }
  function remove(): void {
    window.removeEventListener("pointerdown", unlock, true);
    window.removeEventListener("keydown", unlock, true);
  }
  window.addEventListener("pointerdown", unlock, true);
  window.addEventListener("keydown", unlock, true);
  if (getCurrentScope()) onScopeDispose(remove);
}

/** A few words next to the choice when a notification is chosen and cannot be shown yet (or was refused). */
function useNote(mode: Ref<AlertMode>, refused: Ref<boolean>, permission: Ref<NotificationPermission>, possible: boolean) {
  return computed(() => {
    if (refused.value) return t("settings.alert.note_refused");
    if (!wantsPopup(mode.value) || !possible) return "";
    return permission.value === "denied" ? t("settings.alert.note_blocked") : permission.value === "default" ? t("settings.alert.note_not_yet") : "";
  });
}

export function useBrowserAlerts(openConversation: (call: string) => void) {
  const chime = new Chime();
  const tab = useTabAlert();
  const app = inApp(); // the desktop app's own window, not a browser
  /** In the app's window the daemon's own alert tells (lib/shell.ts), and the window's own does nothing: a choice it kept earlier stays in the browser's memory and is not read. */
  const daemonAlone = daemonTells();

  /** The page is a secure context; where it is not, the way to make it one is shown (PopupHelp). */
  const secure = window.isSecureContext === true;
  /** The browser can show notifications here: a secure context (localhost, https, an address the browser was told to trust) with the API, and not the app's window. */
  const possible = !app && typeof Notification !== "undefined" && secure;
  const permission = ref<NotificationPermission>(permissionNow(possible));
  /** why a notification cannot be chosen, else undefined */
  const why = computed(() => popupWhy(possible, permission.value));
  const mode = ref<AlertMode>(daemonAlone ? "off" : storedMode(isLoopbackHost(location.hostname), popupWhy(possible, permission.value), app)); // (off by default on the loopback)
  /** the permission was refused for the notification that was chosen: said next to the choice, until the next choice */
  const refused = ref(false);
  const popupOn = computed(() => possible && wantsPopup(mode.value) && permission.value === "granted");
  const note = useNote(mode, refused, permission, possible);
  const soundStatus = useStatus();
  const popupStatus = useStatus();

  useAudioUnlock(chime);

  function keep(next: AlertMode): void {
    mode.value = next;
    writeStored(MODE_KEY, next);
  }

  /** Asks the browser for the permission to show notifications, unless it has been asked, and reads the answer. A click only. */
  async function allow(): Promise<boolean> {
    if (!possible) return false;
    if (Notification.permission === "default") permission.value = (await Notification.requestPermission()) ?? Notification.permission;
    else permission.value = Notification.permission;
    return permission.value === "granted";
  }

  /** The choice, a click: a choice with a notification asks for the permission if the browser has not been asked, and falls back to sound alone when it is not given. */
  async function choose(next: AlertMode): Promise<void> {
    if (daemonAlone) return;
    refused.value = false;
    keep(next);
    if (!wantsPopup(next) || (await allow())) return;
    keep("sound");
    refused.value = true;
  }

  /** What an alert does in this browser: the chime when the choice has the sound, and the notifications where they can be shown (`popups` shows them and says which were), else the alert of the browser tab for `call`. */
  function ring(call: string, popups: (failed: () => void) => boolean[], bell = false): void {
    if (mode.value === "off") return;
    if (wantsSound(mode.value)) chime.play();
    const tabAlert = () => tab.start(call, false, bell);
    permission.value = permissionNow(possible); // read now: the person may have blocked notifications in the browser's settings since the page loaded
    const shown = popupOn.value && popups(tabAlert).includes(true);
    if (!shown) tabAlert();
  }

  /** What a message to us does in this browser: the alert, with a notification for each of the latest few. */
  function announce(fresh: readonly Alerted[]): void {
    const last = fresh[fresh.length - 1];
    if (last !== undefined) ring(last.from_call, (failed) => fresh.slice(-POPUPS_MAX).map((message) => showPopup(message, openConversation, failed)));
  }

  /** Test sound, a click: the chime now, whatever the choice is. */
  async function testSound(): Promise<void> {
    const ok = (await chime.unlock()) && chime.play();
    soundStatus.set(ok ? "settings.alert.sound_played" : "settings.alert.sound_locked");
  }

  /** Test notification, a click: a notification now, whatever the choice is (it asks for the permission if the browser has not been asked); where none can be shown it says why, and the browser tab alerts for a few seconds. */
  async function testPopup(): Promise<void> {
    if (!possible) return popupStatus.set("settings.alert.popup_off");
    const failed = () => {
      tab.start(testMessage().from_call, true);
      popupStatus.set("settings.alert.popup_blocked");
    };
    if (!(await allow())) return failed();
    if (showPopup(testMessage(), null, failed)) popupStatus.set("settings.alert.popup_sent");
    else failed();
  }

  return {
    app,
    daemonAlone,
    mode,
    why,
    note,
    popupOn,
    possible,
    secure,
    soundStatus: soundStatus.text,
    popupStatus: popupStatus.text,
    tabTitle: tab.shown,
    announce,
    /** What an alert set on a station does in this browser, as the choice says for a message: the chime, its own notification, or the browser tab with a bell. */
    announceStation: (fired: StationAlertMessage): void => ring(fired.call, (failed) => [showStationPopup(fired, failed)], true),
    choose,
    testSound,
    testPopup,
  };
}

export type BrowserAlerts = ReturnType<typeof useBrowserAlerts>;
