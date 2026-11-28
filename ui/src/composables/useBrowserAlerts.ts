// The alert of this browser for a message to us and for a station alert, and its one choice
// (Settings, "Notifications", "In this browser", kept in localStorage per device): off, sound,
// sound and notification, or notification only. The default is off on the machine the daemon
// runs on (the daemon's own alert command notifies there; on a Mac the window starts at the
// sound) and elsewhere sound and notification where the browser can show one, else sound. The
// sound is the chime (the first click or key press unlocks the audio). Where no notification is
// shown, or it fails, the browser tab alerts (useTabAlert). The permission is asked only in a
// click: on choosing a notification and on Test notification. The Test buttons say what happened
// for a few seconds.
// The desktop app's own window has no notification: nothing in it answers a page that asks for
// one (Qt leaves the question unanswered, WebView2 has no handler). Where the daemon's own alert
// notifies (Linux and Windows, `daemonAlone`) the window's alert does nothing and an earlier
// choice stays unread in storage; on a Mac the window's alert is the chime alone, a stored choice
// with a notification is read without it, and the permission is never asked.
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
import type { ChatFreshMessage, MessageRow, StationAlertMessage } from "@/protocol/protocol";

export type Alerted = Pick<MessageRow, "id" | "from_call" | "text">;

const testMessage = (): Alerted => ({ id: 0, from_call: "NEOAPRS", text: t("settings.alert.test_message") });
/**
 * After a long disconnect many messages can arrive at once: only so many notifications, the rest
 * stay in the page.
 */
const POPUPS_MAX = 5;
const STATUS_MS = 5000;

/**
 * The words after a Test button, cleared after a few seconds; the id is kept so they follow the
 * language.
 */
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

/**
 * Show a browser notification; false if the browser refuses (some phones want a service worker);
 * `failed` is called if it could not show it after all. A click focuses the page and does `then`.
 * A notification with the tag of one on show replaces it without a sound.
 */
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

/**
 * The notification of a message: a click opens the conversation for a real message (`open` given).
 */
function showPopup(message: Alerted, open: ((call: string) => void) | null, failed: () => void): boolean {
  const tag = open !== null ? `neoaprs-${message.id}` : `neoaprs-test-${Date.now()}`;
  return notify(notificationTitle(message.from_call), message.text, tag, () => open?.(message.from_call), failed);
}

/** The notification of a station alert, with its own title so it does not look like a message. */
function showStationPopup(fired: StationAlertMessage, failed: () => void): boolean {
  const tag = `neoaprs-alert-${fired.call}-${fired.kind}-${fired.at}`;
  return notify(t("station.alert.popup_title", { call: fired.call }), firedText(fired), tag, () => undefined, failed);
}

/** The notification of new lines of the chat, one for the lines of one reading; a click opens the tab. */
function showChatPopup(fresh: ChatFreshMessage, open: () => void, failed: () => void): boolean {
  const title =
    fresh.count === 1
      ? t("skeds.chat_popup", { call: fresh.call })
      : t("skeds.chat_popup_more", { n: fresh.count, call: fresh.call });
  return notify(title, fresh.text, `neoaprs-chat-${fresh.id}`, open, failed);
}

/** What the browser lets the page do with notifications now; denied where it cannot show one. */
function permissionNow(possible: boolean): NotificationPermission {
  return possible ? Notification.permission : "denied";
}

/**
 * A browser lets a page make sound only after a click or key press: unlock on the first, then stop
 * listening.
 */
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

function useNote(
  mode: Ref<AlertMode>,
  refused: Ref<boolean>,
  permission: Ref<NotificationPermission>,
  possible: boolean,
) {
  return computed(() => {
    if (refused.value) return t("settings.alert.note_refused");
    if (!wantsPopup(mode.value) || !possible) return "";
    return permission.value === "denied"
      ? t("settings.alert.note_blocked")
      : permission.value === "default"
        ? t("settings.alert.note_not_yet")
        : "";
  });
}

export function useBrowserAlerts(openConversation: (call: string) => void, openChat: () => void = () => undefined) {
  const chime = new Chime();
  const tab = useTabAlert();
  const app = inApp();
  /**
   * In the app's window only the daemon's own alert tells (lib/shell.ts); a stored choice stays
   * unread.
   */
  const daemonAlone = daemonTells();

  const secure = window.isSecureContext === true;
  /** Notifications can be shown: a secure context with the API, and not the app's window. */
  const possible = !app && typeof Notification !== "undefined" && secure;
  const permission = ref<NotificationPermission>(permissionNow(possible));
  const why = computed(() => popupWhy(possible, permission.value));
  const mode = ref<AlertMode>(
    daemonAlone ? "off" : storedMode(isLoopbackHost(location.hostname), popupWhy(possible, permission.value), app),
  );
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

  /**
   * Ask the browser for the permission unless it was asked, and read the answer. Only in a click.
   */
  async function allow(): Promise<boolean> {
    if (!possible) return false;
    if (Notification.permission === "default")
      permission.value = (await Notification.requestPermission()) ?? Notification.permission;
    else permission.value = Notification.permission;
    return permission.value === "granted";
  }

  /**
   * The choice, in a click: a notification choice asks for the permission and falls back to sound
   * if refused.
   */
  async function choose(next: AlertMode): Promise<void> {
    if (daemonAlone) return;
    refused.value = false;
    keep(next);
    if (!wantsPopup(next) || (await allow())) return;
    keep("sound");
    refused.value = true;
  }

  /**
   * The chime if the choice has sound, notifications where they can be shown, else the tab alert
   * for `call`.
   */
  function ring(call: string, popups: (failed: () => void) => boolean[], bell = false): void {
    if (mode.value === "off") return;
    if (wantsSound(mode.value)) chime.play();
    const tabAlert = () => tab.start(call, false, bell);
    permission.value = permissionNow(possible);
    const shown = popupOn.value && popups(tabAlert).includes(true);
    if (!shown) tabAlert();
  }

  function announce(fresh: readonly Alerted[]): void {
    const last = fresh[fresh.length - 1];
    if (last !== undefined)
      ring(last.from_call, (failed) =>
        fresh.slice(-POPUPS_MAX).map((message) => showPopup(message, openConversation, failed)),
      );
  }

  async function testSound(): Promise<void> {
    const ok = (await chime.unlock()) && chime.play();
    soundStatus.set(ok ? "settings.alert.sound_played" : "settings.alert.sound_locked");
  }

  /**
   * Test notification, in a click: a notification now; where none can be shown, say why and alert
   * the tab.
   */
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
    /**
     * What a station alert does in this browser: the chime, its own notification, or the tab bell.
     */
    announceStation: (fired: StationAlertMessage): void =>
      ring(fired.call, (failed) => [showStationPopup(fired, failed)], true),
    /** What new lines of the chat do in this browser: the chimes, a notification, or the tab alert. */
    announceChat: (fresh: ChatFreshMessage): void =>
      ring(fresh.call, (failed) => [showChatPopup(fresh, openChat, failed)]),
    choose,
    testSound,
    testPopup,
  };
}

export type BrowserAlerts = ReturnType<typeof useBrowserAlerts>;
