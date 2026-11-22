<script setup lang="ts">
// The dialog of the path builder (opened by PathBuilder), shown over the dimmed page with
// useDialogFocus keys. It edits a draft of hops that starts as `start`: how far it goes
// (PathReach), the path drawn with the result and a field to type a hop (PathHops), and digipeaters
// to pick (PathChoices). A picked digipeater replaces an alias hop (lib/pathreach.ts `withCall`).
// Use is off while `check` finds a problem or an alias is no path; a path with more hops than the
// network usually allows is only marked. Cancel, the cross, Esc and a press beside the dialog close
// it.
import { computed, ref, useId, watch } from "vue";
import IconButton from "@/components/IconButton.vue";
import InfoTip from "@/components/InfoTip.vue";
import PathChoices from "@/components/PathChoices.vue";
import PathHops from "@/components/PathHops.vue";
import PathReach from "@/components/PathReach.vue";
import { useDialogFocus } from "@/composables/useDialogFocus";
import { t } from "@/i18n";
import { openTip } from "@/lib/infotip";
import { choicesFor, pathOf, reversedRoute } from "@/lib/pathbuilder";
import { homeFirst, meaningOf, splitPath, withCall } from "@/lib/pathreach";
import { LIMITS } from "@/protocol/lists";
import type { StationRow } from "@/protocol/protocol";

const props = defineProps<{
  start: readonly string[];
  /** whether home digipeaters may take the first hop, when the path does not say */
  home: boolean;
  check: (path: string) => string;
  station: string | undefined;
  stations: ReadonlyMap<string, StationRow>;
  now: number;
  /** the button that opened the dialog, which gets the focus back */
  opener: HTMLElement | null;
}>();
const emit = defineEmits<{ use: [path: string]; close: [] }>();

const titleId = useId();
/** The name of the (i): the alias is not translated. */
const tipLabel = computed(() => t("settings.about", { label: "WIDEn-N" }));
const dialog = ref<HTMLElement | null>(null);
const keys = useDialogFocus(dialog, () => emit("close"), { back: () => props.opener });
const draft = ref<string[]>([...props.start]);
const home = ref(homeFirst(props.start) ?? props.home);
const meaning = computed(() => meaningOf(draft.value));
const problem = computed(
  () => props.check(pathOf(draft.value)) || (meaning.value.level === "bad" ? meaning.value.reason : ""),
);
const named = computed(() => splitPath(draft.value).lead);
const offer = computed(
  () =>
    choicesFor(props.stations.values(), named.value) ?? {
      after: named.value[named.value.length - 1] ?? null,
      choices: [],
    },
);
const reversed = computed(() => (props.station === undefined ? null : reversedRoute(props.stations, props.station)));

watch(draft, (hops) => (home.value = homeFirst(hops) ?? home.value));

function add(calls: readonly string[]): void {
  draft.value = [...draft.value, ...calls].slice(0, LIMITS.path.maxCalls);
}

function pick(call: string): void {
  draft.value = withCall(draft.value, call).slice(0, LIMITS.path.maxCalls);
}

function remove(index: number): void {
  draft.value = draft.value.filter((_, i) => i !== index);
}

/**
 * A press on the dimmed page closes the dialog and also closes the (i) note; no press inside goes
 * further.
 */
function press(event: PointerEvent): void {
  event.stopPropagation();
  if (!(event.target instanceof Element && event.target.closest(".infotip"))) openTip.value = null;
  if (event.target === event.currentTarget) emit("close");
}

/** Esc with the (i) note open closes the note only. */
function escapeNote(event: KeyboardEvent): void {
  if (event.key !== "Escape" || openTip.value === null) return;
  event.stopPropagation();
  openTip.value = null;
}
</script>

<template>
  <div
    class="pathbuild-backdrop"
    title=""
    @pointerdown="press"
    @focusin.stop
    @keydown.capture="escapeNote"
    @keydown="keys.onKey"
  >
    <section ref="dialog" class="pathbuild" role="dialog" aria-modal="true" :aria-labelledby="titleId" tabindex="-1">
      <header class="updatedialog-head">
        <h2 :id="titleId" class="pathbuild-title">{{ t("pathbuilder.title") }}</h2>
        <InfoTip class="pathbuild-tip" :label="tipLabel">
          <span class="info-line">{{ t("pathbuilder.tip1") }}</span>
          <span class="info-line">{{ t("pathbuilder.tip2") }}</span>
          <span class="info-line">{{ t("pathbuilder.tip3") }}</span>
          <span class="info-line">{{ t("pathbuilder.tip4") }}</span>
        </InfoTip>
        <IconButton kind="close" :label="t('pathbuilder.cancel')" @click="emit('close')" />
      </header>
      <PathReach :hops="draft" :home="home" @set="draft = $event" @home="home = $event">
        <button
          v-if="station !== undefined"
          type="button"
          class="btn"
          :disabled="reversed === null"
          :title="reversed === null ? t('pathbuilder.no_route') : pathOf(reversed)"
          @click="draft = [...(reversed ?? [])]"
        >
          {{ t("pathbuilder.as_it_comes") }}
        </button>
      </PathReach>
      <PathHops :hops="draft" :meaning="meaning" :problem="problem" @remove="remove" @add="add" />
      <PathChoices :choices="offer.choices" :after="offer.after" :now="now" @pick="pick" />
      <footer class="pathbuild-foot">
        <button
          type="button"
          class="btn primary"
          :disabled="problem !== ''"
          :title="problem || undefined"
          @click="emit('use', pathOf(draft))"
        >
          {{ t("pathbuilder.use") }}
        </button>
        <button type="button" class="btn" @click="emit('close')">{{ t("pathbuilder.cancel") }}</button>
      </footer>
    </section>
  </div>
</template>
