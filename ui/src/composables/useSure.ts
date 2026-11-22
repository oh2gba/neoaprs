// A button that asks twice: the first press arms it ("sure?") and the second, within `ms`, does it
// (`null`: no time limit, for a question armed by an answer, via `arm`). The key says which button
// is armed; arming another disarms the first.
import { getCurrentScope, onScopeDispose, shallowRef } from "vue";

export function useSure<K>(ms: number | null = 5000) {
  const armed = shallowRef<K | null>(null);
  let timer: ReturnType<typeof setTimeout> | undefined;

  function disarm(): void {
    clearTimeout(timer);
    armed.value = null;
  }

  function arm(key: K): void {
    clearTimeout(timer);
    armed.value = key;
    if (ms !== null) timer = setTimeout(disarm, ms);
  }

  function press(key: K, act: () => void): void {
    if (armed.value === key) {
      disarm();
      act();
      return;
    }
    arm(key);
  }

  if (getCurrentScope()) onScopeDispose(() => clearTimeout(timer));
  return { armed, press, arm, disarm };
}
