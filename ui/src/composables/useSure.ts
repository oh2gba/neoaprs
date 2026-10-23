// A button that asks twice: the first press arms it ("sure?") and the second, within `ms`, does it. The key says which of several buttons is armed; arming another disarms the first.
import { getCurrentScope, onScopeDispose, shallowRef } from "vue";

export function useSure<K>(ms = 5000) {
  const armed = shallowRef<K | null>(null);
  let timer: ReturnType<typeof setTimeout> | undefined;

  function disarm(): void {
    clearTimeout(timer);
    armed.value = null;
  }

  /** Arms the button `key`, or (when it is armed) disarms it and runs `act`. */
  function press(key: K, act: () => void): void {
    if (armed.value === key) {
      disarm();
      act();
      return;
    }
    clearTimeout(timer);
    armed.value = key;
    timer = setTimeout(disarm, ms);
  }

  if (getCurrentScope()) onScopeDispose(() => clearTimeout(timer));
  return { armed, press, disarm };
}
