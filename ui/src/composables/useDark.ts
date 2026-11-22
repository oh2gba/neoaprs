// Whether the system prefers a dark colour scheme, kept up to date.
import { onBeforeUnmount, ref } from "vue";

export function useDark() {
  const query = typeof window.matchMedia === "function" ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  const dark = ref(query?.matches ?? false);
  const change = (event: MediaQueryListEvent): void => {
    dark.value = event.matches;
  };
  query?.addEventListener("change", change);
  onBeforeUnmount(() => query?.removeEventListener("change", change));
  return dark;
}
