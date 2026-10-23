// "Install app": a browser that can install the page as an app (Chrome, Edge, Brave, Opera on a computer and on Android) says so with `beforeinstallprompt`, once, early, and the page may then ask for the install when the person
// wants it. The event comes before any component exists, so main.ts starts listening (`listenForInstall`) and the button (InstallApp) reads `useInstall`. A browser that does not say it (Firefox, Safari, a page over plain http) leaves
// the button out; the manifest still lets a phone add the page to its home screen.
import { computed, shallowRef } from "vue";

/** The event of the browsers that install: not in the DOM types. */
export interface InstallPrompt extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

const offered = shallowRef<InstallPrompt | null>(null);

/** Keeps the offer of the browser until it is used, or until the app is installed. Returns the way to stop listening. */
export function listenForInstall(target: Pick<Window, "addEventListener" | "removeEventListener"> = window): () => void {
  const onOffer = (event: Event): void => {
    event.preventDefault(); // the browser's own bar is not shown: the button is the page's
    offered.value = event as InstallPrompt;
  };
  const onInstalled = (): void => {
    offered.value = null;
  };
  target.addEventListener("beforeinstallprompt", onOffer);
  target.addEventListener("appinstalled", onInstalled);
  return () => {
    target.removeEventListener("beforeinstallprompt", onOffer);
    target.removeEventListener("appinstalled", onInstalled);
    offered.value = null;
  };
}

export function useInstall() {
  const canInstall = computed(() => offered.value !== null);

  /** Asks the browser to show its install dialog; the offer is good once, whatever the answer. */
  async function install(): Promise<"accepted" | "dismissed" | "none"> {
    const event = offered.value;
    if (!event) return "none";
    offered.value = null;
    try {
      await event.prompt();
      return (await event.userChoice).outcome;
    } catch {
      return "dismissed";
    }
  }

  return { canInstall, install };
}
