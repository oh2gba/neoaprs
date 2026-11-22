// Encrypted messages on the page: the key each station announced (topic `station_keys`), our own
// key's fingerprint (in the status; present only when the daemon was started with --encryption,
// so it also shows the feature is there: `on`), and the commands: send our key to a station,
// forget a station's key, make a new key. A message can be locked when the feature is there and
// the station has sent its key (`canLock`).
import { computed, type Ref } from "vue";
import type { Command, StationKey, StatusMessage } from "@/protocol/protocol";

export function useStationKeys(keys: ReadonlyMap<string, StationKey>, status: Readonly<Ref<StatusMessage | null>>, send: (command: Command) => boolean) {
  const own = computed(() => status.value?.message_key ?? "");
  const on = computed(() => own.value !== "");
  return {
    on,
    own,
    of: (call: string): StationKey | null => keys.get(call) ?? null,
    canLock: (call: string): boolean => on.value && keys.has(call),
    sendKey: (call: string): boolean => send({ cmd: "send_key", to: call }),
    forget: (call: string): boolean => send({ cmd: "forget_station_key", call }),
    renew: (): boolean => send({ cmd: "message_key_new" }),
  };
}

export type StationKeys = ReturnType<typeof useStationKeys>;
