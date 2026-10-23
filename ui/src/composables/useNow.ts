// The clock the page's ages are held against: one ref that moves on every `every` ms while the component is mounted, so that "3 min" becomes "4 min" without a message from the daemon.
import { onBeforeUnmount, onMounted, ref } from "vue";

export function useNow(every = 5000) {
  const now = ref(Date.now());
  let timer: ReturnType<typeof setInterval> | undefined;
  onMounted(() => {
    now.value = Date.now();
    timer = setInterval(() => (now.value = Date.now()), every);
  });
  onBeforeUnmount(() => clearInterval(timer));
  return now;
}
