// "Install app": a browser that can install the page says so once, early, with
// `beforeinstallprompt`. The event comes before any component exists, so main.ts starts listening
// (`listenForInstall`) and the button reads `useInstall`. Other browsers get no button.
import { computed, shallowRef } from "vue";

export interface InstallPrompt extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

const offered = shallowRef<InstallPrompt | null>(null);

/**
 * Keep the browser's install offer until it is used or the app is installed; return the stop
 * function.
 */
export function listenForInstall(target: Pick<Window, "addEventListener" | "removeEventListener"> = window): () => void {
  const onOffer = (event: Event): void => {
    event.preventDefault();
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

  /** Ask the browser to show its install dialog; the offer is good once, whatever the answer. */
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
