// Tune and the keying test of a radio's modem. Tune asks the daemon for the tune tone, which stops
// by itself after ten seconds or at a second press; Test keys the radio for a second. Both use
// `radio_tune` and `radio_key_test` with the radio's id; with no radio named nothing runs. What is
// under way is read from the modem (`modem.test`), so every page shows it. Both are off while RX
// only is ticked, while the modem is not running, while a frame keys the radio or the channel is
// busy, and while the other one runs.
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
  const why = computed(() => (receiveOnly.value ? rxOnlyReason() : undefined));
  /**
   * The radio is keyed or the channel is busy: the daemon would refuse, so the buttons wait (Tune's
   * Stop stays).
   */
  const held = computed(
    () => modem.value !== null && modem.value.test === "" && (modem.value.keyed || modem.value.busy),
  );
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
