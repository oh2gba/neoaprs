// A word to the user that is no error: the toast "Asked OH2XYZ for its status", "Copied OH2XYZ". One at a time, a new one replaces the one shown (`n` counts up, so that the same words twice are two notices); ToastBar shows it in the place of the daemon's errors.
import { shallowRef } from "vue";

export interface Notice {
  text: string;
  n: number;
}

export function useNotice() {
  const notice = shallowRef<Notice | null>(null);
  let count = 0;
  function say(text: string): void {
    notice.value = { text, n: ++count };
  }
  return { notice, say };
}
