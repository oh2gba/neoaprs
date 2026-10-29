<script setup lang="ts">
// The dialog of the path builder (PathBuilder.vue opens it), in the middle of the page over a dimmed one as the update dialog is, and with its keys (useDialogFocus: the focus in it, Tab going round, Esc closing). It edits a draft
// of hops that starts as `start`: the usual paths one click each (the button's hover title says what each is for), "As its packets come" for a station's Route (its best route turned round, off while none is known), the
// path as chips with the result and a field to type a hop (PathHops), and the digipeaters to go through (PathChoices: the ones we hear for the first hop, the ones next to the hop before for the next, up to three hops; the
// choices of lib/pathbuilder.ts, from the station rows of the page). Use gives the path to the field, off with the field's reason in its title while `check` finds something; Cancel, the cross, Esc and a press beside the
// dialog close it without a word to the field. No line explains anything: the controls are the explanation, the hover titles the rest.
import { computed, ref, useId } from "vue";
import IconButton from "@/components/IconButton.vue";
import PathChoices from "@/components/PathChoices.vue";
import PathHops from "@/components/PathHops.vue";
import { useDialogFocus } from "@/composables/useDialogFocus";
import { t } from "@/i18n";
import { choicesFor, pathOf, PRESETS, reversedRoute } from "@/lib/pathbuilder";
import { LIMITS } from "@/protocol/lists";
import type { StationRow } from "@/protocol/protocol";

const props = defineProps<{
  start: readonly string[];
  check: (path: string) => string;
  station: string | undefined;
  stations: ReadonlyMap<string, StationRow>;
  now: number;
  /** the button that opened it, which gets the focus back */
  opener: HTMLElement | null;
}>();
const emit = defineEmits<{ use: [path: string]; close: [] }>();

const titleId = useId();
const dialog = ref<HTMLElement | null>(null);
const keys = useDialogFocus(dialog, () => emit("close"), { back: () => props.opener });
const draft = ref<string[]>([...props.start]);
const problem = computed(() => props.check(pathOf(draft.value)));
const offer = computed(() => choicesFor(props.stations.values(), draft.value) ?? { after: draft.value[draft.value.length - 1] ?? null, choices: [] });
const reversed = computed(() => (props.station === undefined ? null : reversedRoute(props.stations, props.station)));

function add(calls: readonly string[]): void {
  draft.value = [...draft.value, ...calls].slice(0, LIMITS.path.maxCalls);
}

function remove(index: number): void {
  draft.value = draft.value.filter((_, i) => i !== index);
}

/** A press on the dimmed page beside the dialog closes it; no press in it goes further (to a box under it that closes on a press outside itself). */
function press(event: PointerEvent): void {
  event.stopPropagation();
  if (event.target === event.currentTarget) emit("close");
}
</script>

<template>
  <div class="pathbuild-backdrop" title="" @pointerdown="press" @focusin.stop @keydown="keys.onKey">
    <section ref="dialog" class="pathbuild" role="dialog" aria-modal="true" :aria-labelledby="titleId" tabindex="-1">
      <header class="updatedialog-head">
        <h2 :id="titleId" class="pathbuild-title">{{ t("pathbuilder.title") }}</h2>
        <IconButton kind="close" :label="t('pathbuilder.cancel')" @click="emit('close')" />
      </header>
      <div class="pathbuild-presets" role="group" :aria-label="t('pathbuilder.presets_label')">
        <button v-for="preset in PRESETS" :key="preset.title" type="button" class="btn" :title="t(preset.title)" @click="draft = [...preset.hops]">
          {{ preset.hops.length === 0 ? t("pathbuilder.direct") : preset.hops.join(",") }}
        </button>
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
      </div>
      <PathHops :hops="draft" :problem="problem" @remove="remove" @add="add" />
      <PathChoices :choices="offer.choices" :after="offer.after" :now="now" @pick="add([$event])" />
      <footer class="pathbuild-foot">
        <button type="button" class="btn primary" :disabled="problem !== ''" :title="problem || undefined" @click="emit('use', pathOf(draft))">
          {{ t("pathbuilder.use") }}
        </button>
        <button type="button" class="btn" @click="emit('close')">{{ t("pathbuilder.cancel") }}</button>
      </footer>
    </section>
  </div>
</template>
