// Tune and the keying test of the HF radio, as the Radio group's buttons run them: Tune asks the daemon for the tune tone (`hf_tune`), which stops by itself after ten seconds or at a second press; Test keys the radio for a second (`hf_key_test`).
// What is under way is read from the HF topic (`modem.test`: "tune", "key" or nothing), so that every page shows it. Both are off while RX only is ticked (nothing is sent), while the modem is not running (the status line says why), and
// while the other one runs; the refusals of the daemon land in the toast as every command's do.
import { computed } from "vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { rxOnlyReason } from "@/lib/compose";

export function useHfTests() {
  const { hf, send, receiveOnly } = useDaemonContext();
  const modem = computed(() => hf.value?.modem ?? null);
  const running = computed(() => modem.value?.state === "running");
  const tuning = computed(() => modem.value?.test === "tune");
  const keying = computed(() => modem.value?.test === "key");
  /** Why a button is off, as its hover title; undefined while it is on. */
  const why = computed(() => (receiveOnly.value ? rxOnlyReason() : undefined));
  const tuneOff = computed(() => receiveOnly.value || !running.value || keying.value);
  const testOff = computed(() => receiveOnly.value || !running.value || tuning.value || keying.value);

  function tune(): void {
    if (tuneOff.value) return;
    send({ cmd: "hf_tune", on: !tuning.value });
  }

  function keyTest(): void {
    if (testOff.value) return;
    send({ cmd: "hf_key_test" });
  }

  return { tuning, keying, tuneOff, testOff, why, tune, keyTest };
}
