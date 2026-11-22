<script setup lang="ts">
// The RX only switch at the right end of the header (lib/rxswitch.ts): one press goes to RX only,
// two ("sure?") go back to transmitting. Every face is rendered, so its width never changes
// (TwoWords). A line for a screen reader says the new face, as the button keeps its place.
import { computed, ref, watch } from "vue";
import TagMark from "@/components/TagMark.vue";
import TwoWords from "@/components/TwoWords.vue";
import { useSure } from "@/composables/useSure";
import { t } from "@/i18n";
import type { PillTarget } from "@/lib/pills";
import { RX_SWITCH_ID, type RxSwitch } from "@/lib/rxswitch";

const props = defineProps<{ rx: RxSwitch }>();
const emit = defineEmits<{ transmit: [on: boolean]; open: [target: PillTarget, focus: string] }>();

const sure = useSure<"on">();
const armed = computed(() => sure.armed.value === "on");
watch([() => props.rx.face, () => props.rx.act], () => sure.disarm());

// A confirming press sooner than this after the arming one, or from a held key, is not the
// operator's second press (a double click, a double tap, a repeating Enter).
const CONFIRM_MS = 500;
let armedAt = 0;
let held = false;

function key(event: KeyboardEvent): void {
  held = event.repeat;
  if (event.repeat) event.preventDefault();
}

function release(): void {
  held = false;
}

const said = ref({ text: "", n: 0 });
watch(
  () => props.rx.face,
  (face) => (said.value = { text: t(face === "rx" ? "pill.rx" : "header.rx.tx"), n: said.value.n + 1 }),
);

function press(): void {
  if (held) return;
  if (props.rx.act === "open") emit("open", "settings", props.rx.focus);
  if (props.rx.act !== "toggle") return;
  if (props.rx.face === "tx") return emit("transmit", false);
  if (armed.value && Date.now() - armedAt < CONFIRM_MS) return;
  if (!armed.value) armedAt = Date.now();
  sure.press("on", () => emit("transmit", true));
}
</script>

<template>
  <span class="sr-only" role="status" aria-live="polite"
    ><span :key="said.n">{{ said.text }}</span></span
  >
  <TagMark
    :id="RX_SWITCH_ID"
    as="button"
    class="rxswitch"
    :tone="rx.face === 'rx' ? 'warn' : 'neutral'"
    :title="t(rx.title)"
    :disabled="rx.act === 'none'"
    @click="press"
    @keydown="key"
    @keyup="release"
    @blur="release"
    ><TwoWords :second="rx.face === 'rx'"
      ><template #first>{{ t("header.rx.tx") }}</template
      ><template #second
        ><TwoWords :second="armed"
          ><template #first>{{ t("pill.rx") }}</template
          ><template #second>{{ t("header.rx.sure") }}</template></TwoWords
        ></template
      ></TwoWords
    ></TagMark
  >
</template>
