// Calls `shown` when an element comes into view: when its tab is opened, when the fold it is in is unfolded, when it is scrolled to (an IntersectionObserver), at most once in `everyMs`, and once when it is made where there is no observer. For
// the rows that ask the daemon for something fresh when the person looks at them (the HF box's suggested frequencies).
import { onBeforeUnmount, onMounted, type Ref } from "vue";

export function useWhenShown(target: Readonly<Ref<HTMLElement | null>>, shown: () => void, everyMs = 60_000): void {
  let last = Number.NEGATIVE_INFINITY;
  let observer: IntersectionObserver | null = null;
  const fire = (): void => {
    const now = Date.now();
    if (now - last < everyMs) return;
    last = now;
    shown();
  };
  onMounted(() => {
    if (typeof IntersectionObserver !== "function" || target.value === null) {
      fire();
      return;
    }
    observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) fire();
    });
    observer.observe(target.value);
  });
  onBeforeUnmount(() => observer?.disconnect());
}
