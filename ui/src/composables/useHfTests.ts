// Tune and the keying test of a radio's modem, as the Radio group's buttons run them: Tune asks the daemon for the tune tone, which stops by itself after ten seconds or at a second press; Test keys the radio for a second.
// The radio is asked by `radio_tune` and `radio_key_test` with its id, and read from its row; with no radio named there is nothing to run.
// What is under way is read from the modem (`modem.test`: "tune", "key" or nothing), so that every page shows it. Both are off while RX only is ticked (nothing is sent), while the modem is not running (the status line says why), while a frame keys the radio or the channel is busy, and
// while the other one runs; the refusals of the daemon land in the toast as every command's do.
import { computed } from "vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { rxOnlyReason } from "@/lib/compose";
import type { PageRadio } from "@/lib/radios";

export function useHfTests(radio: () => PageRadio | null = () => null) {
  const { send, receiveOnly } = useDaemonContext();
  const modem = computed(() => radio()?.row.modem ?? null);
  const running = computed(() => modem.value?.state === "running");
  const tuning = computed(() => modem.value?.test === "tune");
  const keying = computed(() => modem.value?.test === "key");
  /** Why a button is off, as its hover title; undefined while it is on. */
  const why = computed(() => (receiveOnly.value ? rxOnlyReason() : undefined));
  /** The radio is keyed by a frame of ours or the channel is heard busy: the daemon would refuse, and the operator can only wait, so the buttons wait (the tone of Tune keys the radio too, and its Stop stays). */
  const held = computed(() => modem.value !== null && modem.value.test === "" && (modem.value.keyed || modem.value.busy));
  const tuneOff = computed(() => receiveOnly.value || !running.value || keying.value || held.value);
  const testOff = computed(() => receiveOnly.value || !running.value || tuning.value || keying.value || held.value);

  function tune(): void {
    const id = radio()?.id;
    if (tuneOff.value || id === undefined) return;
    send({ cmd: "radio_tune", radio: id, on: !tuning.value });
  }

  function keyTest(): void {
    const id = radio()?.id;
    if (testOff.value || id === undefined) return;
    send({ cmd: "radio_key_test", radio: id });
  }

  return { tuning, keying, tuneOff, testOff, why, tune, keyTest };
}
