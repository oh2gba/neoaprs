// The alert of this browser for a message to us, and its switches (the Settings tab, "This browser"; kept in localStorage, so each device decides): the web alert as a whole, which is off by default on the machine the
// daemon runs on (the page on the loopback, the desktop app: the daemon's own alert command notifies there) and on for a page opened from another device, then Sound and Notifications. A notification, where the browser
// allows one (a secure context, permission given), is the alert, and the system plays its own sound; where none can be shown the page plays the chime (the first click or key press unlocks the audio) and the browser tab
// alerts (useTabAlert). The permission is asked only when the Notifications switch is turned on.
import { computed, onScopeDispose, getCurrentScope, ref } from "vue";
import { usePersistedFlag } from "@/composables/usePersisted";
import { useTabAlert } from "@/composables/useTabAlert";
import { Chime } from "@/lib/chime";
import { isLoopbackHost, notificationTitle } from "@/lib/pagealert";
import type { MessageRow } from "@/protocol/protocol";

/** What an alert needs of a message. */
export type Alerted = Pick<MessageRow, "id" | "from_call" | "text">;

const TEST_MESSAGE: Alerted = { id: 0, from_call: "NEOAPRS", text: "This is a test of the NeoAPRS alert" };
/** After a long disconnect many messages can arrive at once: so many notifications, the rest are in the page. */
const NOTIFICATIONS_MAX = 5;
const ON_OFF = ["on", "off"] as const;

export function useBrowserAlerts(openConversation: (call: string) => void) {
  const chime = new Chime();
  const tab = useTabAlert();
  const here = isLoopbackHost(location.hostname);
  const enabled = usePersistedFlag("alert.web", ON_OFF, !here);
  const sound = usePersistedFlag("alert.sound", ON_OFF, true);
  const wanted = usePersistedFlag("alert.notify", ON_OFF, true);

  /** The browser can show notifications here: a secure context (localhost, https, an address the browser was told to trust) with the API. */
  const possible = typeof Notification !== "undefined" && window.isSecureContext === true;
  const permission = ref<NotificationPermission>(possible ? Notification.permission : "denied");
  const notifyOn = computed(() => possible && wanted.value && permission.value === "granted");
  const notifyTitle = computed(() =>
    !possible ? "Needs https or localhost" : permission.value === "denied" ? "Blocked in the browser's settings" : undefined,
  );

  function unlock(): void {
    void chime.unlock().then((ok) => {
      if (ok) removeUnlock();
    });
  }
  function removeUnlock(): void {
    window.removeEventListener("pointerdown", unlock, true);
    window.removeEventListener("keydown", unlock, true);
  }
  window.addEventListener("pointerdown", unlock, true);
  window.addEventListener("keydown", unlock, true);
  if (getCurrentScope()) onScopeDispose(removeUnlock);

  /** The Notifications switch, a click: turning it on asks for the permission if the browser has not been asked, and goes back off when it is not given. */
  async function setNotify(on: boolean): Promise<void> {
    wanted.value = on;
    if (!on || !possible) return;
    if (Notification.permission === "default") permission.value = (await Notification.requestPermission()) ?? Notification.permission;
    else permission.value = Notification.permission;
    if (permission.value !== "granted") wanted.value = false;
  }

  /** Shows the notification of a message; false when the browser refuses (some, on a phone, want a service worker). A click focuses the page and opens the conversation. */
  function show(message: Alerted, open: boolean): boolean {
    try {
      const note = new Notification(notificationTitle(message.from_call), { body: message.text, tag: `neoaprs-${message.id}` });
      note.onclick = () => {
        window.focus();
        note.close();
        if (open) openConversation(message.from_call);
      };
      return true;
    } catch {
      return false;
    }
  }

  /** What a message to us does in this browser: a notification where one can be shown, else the chime and the alert of the browser tab. */
  function announce(fresh: readonly Alerted[], test = false): void {
    const last = fresh[fresh.length - 1];
    if (!enabled.value || last === undefined) return;
    const shown =
      notifyOn.value &&
      fresh
        .slice(-NOTIFICATIONS_MAX)
        .map((message) => show(message, !test))
        .includes(true);
    if (shown) return;
    if (sound.value) chime.play();
    tab.start(last.from_call, test);
  }

  /** The Test button, a click: the same as a message to us. */
  async function test(): Promise<void> {
    await chime.unlock();
    announce([TEST_MESSAGE], true);
  }

  return { enabled, sound, notifyOn, notifyTitle, possible, tabTitle: tab.shown, announce, setNotify, test };
}

export type BrowserAlerts = ReturnType<typeof useBrowserAlerts>;
