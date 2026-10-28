// The alert of this browser for a message to us and for an alert set on a station (which says what happened and is no message: its own pop-up title, a bell in the browser tab), and its one choice (the Settings tab, "Notifications", "In this browser"; kept in localStorage, so each device decides): off, sound, sound and pop-up, or pop-up only. It is off by
// default on the machine the daemon runs on (the page on the loopback, the desktop app: the daemon's own alert command notifies there), and elsewhere sound and pop-up where the browser can show one, else sound. The sound is
// the chime (the first click or key press unlocks the audio); a pop-up is a notification of the browser, shown where it allows one (a secure context, permission given), and where none is shown, or the browser fails to show it, the
// browser tab alerts (useTabAlert). The permission is asked only in a click: on choosing a pop-up, and on the Test pop-up button. Test sound and Test pop-up each say, for a few seconds, what happened.
import { computed, onScopeDispose, getCurrentScope, ref } from "vue";
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import { useTabAlert } from "@/composables/useTabAlert";
import { Chime } from "@/lib/chime";
import { storedMode, popupWhy, wantsPopup, wantsSound, MODE_KEY, type AlertMode } from "@/lib/alertmode";
import { isLoopbackHost, notificationTitle } from "@/lib/pagealert";
import { writeStored } from "@/lib/storage";
import { firedText } from "@/lib/stationalert";
import type { MessageRow, StationAlertMessage } from "@/protocol/protocol";

/** What an alert needs of a message. */
export type Alerted = Pick<MessageRow, "id" | "from_call" | "text">;

/** The message of the Test pop-up, in the language of the page. */
const testMessage = (): Alerted => ({ id: 0, from_call: "NEOAPRS", text: t("settings.alert.test_message") });
/** After a long disconnect many messages can arrive at once: so many pop-ups, the rest are in the page. */
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

/** Shows a pop-up of the browser; false when the browser refuses (some, on a phone, want a service worker), and `failed` is called when it could not show it after all. A click focuses the page and does `then`. A pop-up
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

/** The pop-up of a message: a click on it opens the conversation for a real message (`open` is given). A test has a tag of its own each time. */
function showPopup(message: Alerted, open: ((call: string) => void) | null, failed: () => void): boolean {
  const tag = open !== null ? `neoaprs-${message.id}` : `neoaprs-test-${Date.now()}`;
  return notify(notificationTitle(message.from_call), message.text, tag, () => open?.(message.from_call), failed);
}

/** The pop-up of an alert set on a station ("APRS alert: OH2XYZ", "OH2XYZ is on the air"): its own title, so that it does not look like a message; a click brings the page to the front. */
function showStationPopup(fired: StationAlertMessage, failed: () => void): boolean {
  const tag = `neoaprs-alert-${fired.call}-${fired.kind}-${fired.at}`;
  return notify(t("station.alert.popup_title", { call: fired.call }), firedText(fired), tag, () => undefined, failed);
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

export function useBrowserAlerts(openConversation: (call: string) => void) {
  const chime = new Chime();
  const tab = useTabAlert();
  const here = isLoopbackHost(location.hostname);

  /** The page is a secure context; where it is not, the way to make it one is shown (PopupHelp). */
  const secure = window.isSecureContext === true;
  /** The browser can show pop-ups here: a secure context (localhost, https, an address the browser was told to trust) with the API. */
  const possible = typeof Notification !== "undefined" && secure;
  const permission = ref<NotificationPermission>(possible ? Notification.permission : "denied");
  /** why a pop-up cannot be chosen, else undefined */
  const why = computed(() => popupWhy(possible, permission.value));
  const mode = ref<AlertMode>(storedMode(here, popupWhy(possible, permission.value)));
  /** the permission was refused for the pop-up that was chosen: said next to the choice, until the next choice */
  const refused = ref(false);
  const popupOn = computed(() => possible && wantsPopup(mode.value) && permission.value === "granted");
  /** a few words next to the choice when a pop-up is chosen and cannot be shown yet */
  const note = computed(() => {
    if (refused.value) return t("settings.alert.note_refused");
    if (!wantsPopup(mode.value) || !possible) return "";
    return permission.value === "denied" ? t("settings.alert.note_blocked") : permission.value === "default" ? t("settings.alert.note_not_yet") : "";
  });
  const soundStatus = useStatus();
  const popupStatus = useStatus();

  useAudioUnlock(chime);

  function keep(next: AlertMode): void {
    mode.value = next;
    writeStored(MODE_KEY, next);
  }

  /** Asks the browser for the permission to show pop-ups, unless it has been asked, and reads the answer. A click only. */
  async function allow(): Promise<boolean> {
    if (!possible) return false;
    if (Notification.permission === "default") permission.value = (await Notification.requestPermission()) ?? Notification.permission;
    else permission.value = Notification.permission;
    return permission.value === "granted";
  }

  /** The choice, a click: a choice with a pop-up asks for the permission if the browser has not been asked, and falls back to sound alone when it is not given. */
  async function choose(next: AlertMode): Promise<void> {
    refused.value = false;
    keep(next);
    if (!wantsPopup(next) || (await allow())) return;
    keep("sound");
    refused.value = true;
  }

  /** What an alert does in this browser: the chime when the choice has the sound, and the pop-ups where they can be shown (`popups` shows them and says which were), else the alert of the browser tab for `call`. */
  function ring(call: string, popups: (failed: () => void) => boolean[], bell = false): void {
    if (mode.value === "off") return;
    if (wantsSound(mode.value)) chime.play();
    const tabAlert = () => tab.start(call, false, bell);
    const shown = popupOn.value && popups(tabAlert).includes(true);
    if (!shown) tabAlert();
  }

  /** What a message to us does in this browser: the alert, with a pop-up for each of the latest few. */
  function announce(fresh: readonly Alerted[]): void {
    const last = fresh[fresh.length - 1];
    if (last !== undefined) ring(last.from_call, (failed) => fresh.slice(-POPUPS_MAX).map((message) => showPopup(message, openConversation, failed)));
  }

  /** Test sound, a click: the chime now, whatever the choice is. */
  async function testSound(): Promise<void> {
    const ok = (await chime.unlock()) && chime.play();
    soundStatus.set(ok ? "settings.alert.sound_played" : "settings.alert.sound_locked");
  }

  /** Test pop-up, a click: a pop-up now, whatever the choice is (it asks for the permission if the browser has not been asked); where none can be shown it says why, and the browser tab alerts for a few seconds. */
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
    /** What an alert set on a station does in this browser, as the choice says for a message: the chime, its own pop-up, or the browser tab with a bell. */
    announceStation: (fired: StationAlertMessage): void => ring(fired.call, (failed) => [showStationPopup(fired, failed)], true),
    choose,
    testSound,
    testPopup,
  };
}

export type BrowserAlerts = ReturnType<typeof useBrowserAlerts>;
