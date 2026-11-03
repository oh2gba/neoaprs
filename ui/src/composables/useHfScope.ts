// The scope of the HF radio's box: the fold's state (remembered in this browser, folded at first), when the page asks the daemon for the pictures (`hf_scope`: only while the fold is open, this page is in front and the modem has the interface that
// makes them, `modem.scope`; asked again when the socket was open anew, since the daemon forgets a page that left), the picture to draw (never one from before the asking), and the receive level that goes with it, held at the last received one
// while the radio transmits (the spectrum is then of our own signal).
import { computed, onBeforeUnmount, ref, shallowRef, watch } from "vue";
import { usePersistedFlag } from "@/composables/usePersisted";
import { useVisible } from "@/composables/useVisible";
import { useDaemonContext } from "@/composables/useDaemonContext";
import type { HfScopeMessage } from "@/protocol/protocol";

export function useHfScope() {
  const { hf, hfScope, send, connection } = useDaemonContext();
  const open = usePersistedFlag("settings.fold.hf-scope", ["open", "folded"], false);
  const visible = useVisible();
  const available = computed(() => hf.value?.modem?.scope === true);
  const wanted = computed(() => open.value && visible.value && available.value && connection.value === "open");
  const stale = shallowRef<HfScopeMessage | null>(null); // the picture that was there when the asking began: not drawn
  const lastReceived = ref<number | null>(null);

  onBeforeUnmount(() => {
    if (wanted.value) send({ cmd: "hf_scope", on: false });
  });
  watch(
    wanted,
    (on) => {
      if (on) stale.value = hfScope.value;
      send({ cmd: "hf_scope", on });
    },
    { immediate: false },
  );
  // the socket is open anew with the fold open: the daemon does not know this page asked
  watch(connection, (state) => {
    if (state === "open" && wanted.value) send({ cmd: "hf_scope", on: true });
  });
  if (wanted.value) {
    stale.value = hfScope.value;
    send({ cmd: "hf_scope", on: true });
  }

  const picture = computed<HfScopeMessage | null>(() => (wanted.value && hfScope.value !== stale.value ? hfScope.value : null));
  watch(picture, (p) => {
    if (p !== null && !p.tx) lastReceived.value = p.level;
  });
  const level = computed<number | null>(() => lastReceived.value);
  const transmitting = computed(() => picture.value?.tx === true);
  return { open, available, wanted, picture, level, transmitting };
}
