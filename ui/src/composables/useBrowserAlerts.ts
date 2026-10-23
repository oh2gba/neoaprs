// The alert of this browser for a message to us, and its one choice (the Settings tab, "Notifications", "In this browser"; kept in localStorage, so each device decides): off, sound, sound and pop-up, or pop-up only. It is off by
// default on the machine the daemon runs on (the page on the loopback, the desktop app: the daemon's own alert command notifies there), and elsewhere sound and pop-up where the browser can show one, else sound. The sound is
// the chime (the first click or key press unlocks the audio); a pop-up is a notification of the browser, shown where it allows one (a secure context, permission given), and where none is shown, or the browser fails to show it, the
// browser tab alerts (useTabAlert). The permission is asked only in a click: on choosing a pop-up, and on the Test pop-up button. Test sound and Test pop-up each say, for a few seconds, what happened.
import { computed, onScopeDispose, getCurrentScope, ref } from "vue";
import { useTabAlert } from "@/composables/useTabAlert";
import { Chime } from "@/lib/chime";
import { storedMode, popupWhy, wantsPopup, wantsSound, MODE_KEY, type AlertMode } from "@/lib/alertmode";
import { isLoopbackHost, notificationTitle } from "@/lib/pagealert";
import { writeStored } from "@/lib/storage";
import type { MessageRow } from "@/protocol/protocol";

/** What an alert needs of a message. */
export type Alerted = Pick<MessageRow, "id" | "from_call" | "text">;

const TEST_MESSAGE: Alerted = { id: 0, from_call: "NEOAPRS", text: "This is a test of the NeoAPRS alert" };
/** After a long disconnect many messages can arrive at once: so many pop-ups, the rest are in the page. */
const POPUPS_MAX = 5;
const STATUS_MS = 5000;

/** The words after a Test button, which go after a few seconds. */
function useStatus() {
  const text = ref("");
  let timer: ReturnType<typeof setTimeout> | undefined;
  const set = (words: string): void => {
    text.value = words;
    clearTimeout(timer);
    timer = setTimeout(() => (text.value = ""), STATUS_MS);
  };
  if (getCurrentScope()) onScopeDispose(() => clearTimeout(timer));
  return { text, set };
}

/** Shows the pop-up of a message; false when the browser refuses (some, on a phone, want a service worker), and `failed` is called when it could not show it after all. A click focuses the page and, for a real
 *  message (`open` is given), opens the conversation. A test has a tag of its own each time: a pop-up with the tag of one still on show replaces it without a sound. */
function showPopup(message: Alerted, open: ((call: string) => void) | null, failed: () => void): boolean {
  try {
    const tag = open !== null ? `neoaprs-${message.id}` : `neoaprs-test-${Date.now()}`;
    const popup = new Notification(notificationTitle(message.from_call), { body: message.text, tag });
    popup.onerror = failed;
    popup.onclick = () => {
      window.focus();
      popup.close();
      open?.(message.from_call);
    };
    return true;
  } catch {
    return false;
  }
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

  /** The browser can show pop-ups here: a secure context (localhost, https, an address the browser was told to trust) with the API. */
  const possible = typeof Notification !== "undefined" && window.isSecureContext === true;
  const permission = ref<NotificationPermission>(possible ? Notification.permission : "denied");
  /** why a pop-up cannot be chosen, else undefined */
  const why = computed(() => popupWhy(possible, permission.value));
  const mode = ref<AlertMode>(storedMode(here, popupWhy(possible, permission.value)));
  /** what was said of a refused permission, next to the choice, until the next choice */
  const refused = ref("");
  const popupOn = computed(() => possible && wantsPopup(mode.value) && permission.value === "granted");
  /** a few words next to the choice when a pop-up is chosen and cannot be shown yet */
  const note = computed(() => {
    if (refused.value !== "") return refused.value;
    if (!wantsPopup(mode.value) || !possible) return "";
    return permission.value === "denied" ? "pop-ups blocked" : permission.value === "default" ? "pop-ups not allowed yet" : "";
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
    refused.value = "";
    keep(next);
    if (!wantsPopup(next) || (await allow())) return;
    keep("sound");
    refused.value = "pop-ups refused: sound only";
  }

  /** What a message to us does in this browser: the chime when the choice has the sound, and a pop-up where one can be shown, else the alert of the browser tab. */
  function announce(fresh: readonly Alerted[]): void {
    const last = fresh[fresh.length - 1];
    if (mode.value === "off" || last === undefined) return;
    if (wantsSound(mode.value)) chime.play();
    const tabAlert = () => tab.start(last.from_call);
    const shown =
      popupOn.value &&
      fresh
        .slice(-POPUPS_MAX)
        .map((message) => showPopup(message, openConversation, tabAlert))
        .includes(true);
    if (!shown) tabAlert();
  }

  /** Test sound, a click: the chime now, whatever the choice is. */
  async function testSound(): Promise<void> {
    const ok = (await chime.unlock()) && chime.play();
    soundStatus.set(ok ? "played" : "sound locked: click the page once");
  }

  /** Test pop-up, a click: a pop-up now, whatever the choice is (it asks for the permission if the browser has not been asked); where none can be shown it says why, and the browser tab alerts for a few seconds. */
  async function testPopup(): Promise<void> {
    if (!possible) return popupStatus.set("needs https or localhost");
    const failed = () => {
      tab.start(TEST_MESSAGE.from_call, true);
      popupStatus.set("pop-up blocked");
    };
    if (!(await allow())) return failed();
    if (showPopup(TEST_MESSAGE, null, failed)) popupStatus.set("pop-up sent");
    else failed();
  }

  return {
    mode,
    why,
    note,
    popupOn,
    possible,
    soundStatus: soundStatus.text,
    popupStatus: popupStatus.text,
    tabTitle: tab.shown,
    announce,
    choose,
    testSound,
    testPopup,
  };
}

export type BrowserAlerts = ReturnType<typeof useBrowserAlerts>;
