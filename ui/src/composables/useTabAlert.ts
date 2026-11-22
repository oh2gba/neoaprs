// The alert of the browser tab while the person is elsewhere: with the page hidden or unfocused
// the title alternates between "✉ OH2DPN" (a station alert: "🔔 OH2XYZ") and the usual one
// (useTitle) and the icon has a red dot, until the page is seen again. A test does the same for a
// few seconds.
import { computed, getCurrentScope, onScopeDispose, ref } from "vue";
import { DOT_ICON, flashTitle } from "@/lib/pagealert";

const BEAT_MS = 1000;
const TEST_MS = 4000;

function isAway(): boolean {
  return document.visibilityState === "hidden" || !document.hasFocus();
}

export function useTabAlert() {
  const words = ref<string | null>(null);
  const beat = ref(false);
  const shown = computed(() => (words.value !== null && beat.value ? words.value : null));
  let timer: ReturnType<typeof setInterval> | undefined;
  let ending: ReturnType<typeof setTimeout> | undefined;
  let testing = false;
  let original: string | null = null;
  let made: HTMLLinkElement | null = null;

  function icon(dot: boolean): void {
    let link = document.querySelector<HTMLLinkElement>('link[rel~="icon"]');
    if (dot) {
      if (link === null) {
        link = document.createElement("link");
        link.rel = "icon";
        document.head.append(link);
        made = link;
      }
      original ??= link.getAttribute("href") ?? "";
      link.setAttribute("href", DOT_ICON);
      return;
    }
    if (link !== null && original !== null) link.setAttribute("href", original);
    made?.remove();
    made = null;
    original = null;
  }

  function stop(): void {
    clearInterval(timer);
    clearTimeout(ending);
    timer = undefined;
    testing = false;
    words.value = null;
    beat.value = false;
    icon(false);
  }

  /**
   * Start alerting for a message from `from` (with `bell`, for a station alert) when the page is in
   * the background.
   */
  function start(from: string, test = false, bell = false): void {
    if (!test && !isAway()) return;
    words.value = flashTitle(from, bell);
    beat.value = true;
    icon(true);
    if (timer === undefined) timer = setInterval(() => (beat.value = !beat.value), BEAT_MS);
    clearTimeout(ending);
    testing = test;
    if (test) ending = setTimeout(stop, TEST_MS);
  }

  function seen(): void {
    if (words.value !== null && !testing && !isAway()) stop();
  }

  document.addEventListener("visibilitychange", seen);
  window.addEventListener("focus", seen);
  if (getCurrentScope()) {
    onScopeDispose(() => {
      document.removeEventListener("visibilitychange", seen);
      window.removeEventListener("focus", seen);
      stop();
    });
  }

  return { shown, start, stop };
}
