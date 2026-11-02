// Encrypted messages on the page: the key each station announced (the topic `station_keys`, which the daemon keeps on first hearing), our own key's fingerprint (in the status; the daemon has one only when it was started with
// --encryption, so the fingerprint is also the sign that the feature is there: `on`), and the commands: send our key to a station, forget a station's key, make a new key of ours. A message to a station can be locked when
// the feature is there and the station has sent its key (`canLock`).
import { computed, type Ref } from "vue";
import type { Command, StationKey, StatusMessage } from "@/protocol/protocol";

export function useStationKeys(keys: ReadonlyMap<string, StationKey>, status: Readonly<Ref<StatusMessage | null>>, send: (command: Command) => boolean) {
  /** The fingerprint of our own key; empty while there is none. */
  const own = computed(() => status.value?.message_key ?? "");
  /** Encrypted messages are there: the daemon was started with --encryption and has a key. */
  const on = computed(() => own.value !== "");
  return {
    on,
    own,
    /** The key a station announced, null for none. */
    of: (call: string): StationKey | null => keys.get(call) ?? null,
    /** Whether a message to the station can be locked: the feature is there and the station has sent its key. */
    canLock: (call: string): boolean => on.value && keys.has(call),
    sendKey: (call: string): boolean => send({ cmd: "send_key", to: call }),
    forget: (call: string): boolean => send({ cmd: "forget_station_key", call }),
    renew: (): boolean => send({ cmd: "message_key_new" }),
  };
}

export type StationKeys = ReturnType<typeof useStationKeys>;
