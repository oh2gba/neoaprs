// A ref that is remembered in localStorage (lib/storage.ts): read when it is made, written when it changes.
import { computed, ref, watch, type Ref, type WritableComputedRef } from "vue";
import { readStored, readStoredNumber, writeStored } from "@/lib/storage";

/** A text that is one of `allowed` (anything else that was stored is ignored). */
export function usePersisted<T extends string>(key: string, fallback: T, allowed: readonly T[]): Ref<T> {
  const stored = readStored(key);
  const value = ref(allowed.find((a) => a === stored) ?? fallback) as Ref<T>;
  watch(value, (v) => writeStored(key, v));
  return value;
}

/** A yes or no, remembered as one of two words (`words` is the word for yes, then the one for no); anything else that was stored is `fallback`. */
export function usePersistedFlag(key: string, words: readonly [yes: string, no: string], fallback: boolean): WritableComputedRef<boolean> {
  const [yes, no] = words;
  const stored = usePersisted(key, fallback ? yes : no, words);
  return computed({ get: () => stored.value === yes, set: (value: boolean) => (stored.value = value ? yes : no) });
}

export function usePersistedNumber(key: string, fallback: number, min: number, max: number): Ref<number> {
  const value = ref(readStoredNumber(key, fallback, min, max));
  watch(value, (v) => writeStored(key, String(v)));
  return value;
}
