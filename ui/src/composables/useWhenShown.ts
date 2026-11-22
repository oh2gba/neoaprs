// Calls `shown` when an element comes into view (and `useInView`, whether it is in view now): when
// its tab opens, its fold unfolds or it is scrolled to (IntersectionObserver), at most once in
// `everyMs`, and once when made where there is no observer. For rows that ask the daemon for
// something fresh when looked at.
import { onBeforeUnmount, onMounted, ref, type Ref } from "vue";

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

/** Whether the element is in view now; in view from its making where there is no observer. */
export function useInView(target: Readonly<Ref<HTMLElement | null>>): Readonly<Ref<boolean>> {
  const inView = ref(false);
  let observer: IntersectionObserver | null = null;
  onMounted(() => {
    if (typeof IntersectionObserver !== "function" || target.value === null) {
      inView.value = true;
      return;
    }
    observer = new IntersectionObserver((entries) => {
      const last = entries[entries.length - 1];
      if (last !== undefined) inView.value = last.isIntersecting;
    });
    observer.observe(target.value);
  });
  onBeforeUnmount(() => observer?.disconnect());
  return inView;
}
