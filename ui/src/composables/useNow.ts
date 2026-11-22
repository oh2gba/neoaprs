// The clock the page's ages are held against: one ref that moves every `every` ms while mounted.
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
