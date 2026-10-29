<script setup lang="ts">
// The dialog of the path builder (PathBuilder.vue opens it), in the middle of the page over a dimmed one as the update dialog is, and with its keys (useDialogFocus: the focus in it, Tab going round, Esc closing). It edits a draft
// of hops that starts as `start`: how far it goes (PathReach: Hops, Direct to 3 in all, and whether home digipeaters may take the first hop, which starts as `home` and follows a path that starts with an alias), "As its packets
// come" beside them for a station's Route (its best route turned round, off while none is known), the path drawn as what it means with the result, its number of hops and a field to type a hop (PathHops), and the digipeaters
// to go through (PathChoices: the ones we hear for the first named hop, the ones next to the hop before for the next, up to three; the choices of lib/pathbuilder.ts, from the station rows of the page). A digipeater picked
// goes after the ones named and takes the place of an alias hop (lib/pathreach.ts `withCall`), so that the number of hops chosen stays. Use gives the path to the field; it is off, with the reason in its title, while `check`
// (the field's rule) finds something or an alias is no path (WIDE1-2), and not for a path of more hops than the network usually allows, which is only marked. Cancel, the cross, Esc and a press beside the dialog close it without
// a word to the field. No line explains anything: the controls and the picture are the explanation, the hover titles the rest, and the one (i) of the header a short guide to WIDEn-N; Esc and a press elsewhere in the dialog
// close its note first.
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
  /** the button that opened it, which gets the focus back */
  opener: HTMLElement | null;
}>();
const emit = defineEmits<{ use: [path: string]; close: [] }>();

const titleId = useId();
/** The name of the (i): the alias it is about is no word to translate. */
const tipLabel = computed(() => t("settings.about", { label: "WIDEn-N" }));
const dialog = ref<HTMLElement | null>(null);
const keys = useDialogFocus(dialog, () => emit("close"), { back: () => props.opener });
const draft = ref<string[]>([...props.start]);
const home = ref(homeFirst(props.start) ?? props.home);
const meaning = computed(() => meaningOf(draft.value));
const problem = computed(() => props.check(pathOf(draft.value)) || (meaning.value.level === "bad" ? meaning.value.reason : ""));
const named = computed(() => splitPath(draft.value).lead);
const offer = computed(() => choicesFor(props.stations.values(), named.value) ?? { after: named.value[named.value.length - 1] ?? null, choices: [] });
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

/** A press on the dimmed page beside the dialog closes it; no press in it goes further (to a box under it that closes on a press outside itself), and one outside the (i) closes its note. */
function press(event: PointerEvent): void {
  event.stopPropagation();
  if (!(event.target instanceof Element && event.target.closest(".infotip"))) openTip.value = null;
  if (event.target === event.currentTarget) emit("close");
}

/** Esc with the (i)'s note open closes the note only. */
function escapeNote(event: KeyboardEvent): void {
  if (event.key !== "Escape" || openTip.value === null) return;
  event.stopPropagation();
  openTip.value = null;
}
</script>

<template>
  <div class="pathbuild-backdrop" title="" @pointerdown="press" @focusin.stop @keydown.capture="escapeNote" @keydown="keys.onKey">
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
        <button type="button" class="btn primary" :disabled="problem !== ''" :title="problem || undefined" @click="emit('use', pathOf(draft))">
          {{ t("pathbuilder.use") }}
        </button>
        <button type="button" class="btn" @click="emit('close')">{{ t("pathbuilder.cancel") }}</button>
      </footer>
    </section>
  </div>
</template>
