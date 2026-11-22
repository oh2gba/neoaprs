<script setup lang="ts">
// The Objects tab: three group boxes, the tab scrolling as a whole: **Add an object**
// (ObjectForm.vue), **My objects** (ours, oldest first, with category tag, send count, next send
// and, while several radios are on, the radios it goes out on as tags like Stations' "Heard on")
// and **Local info** (ObjectsQru.vue). The delete button kills the object (second press after
// "sure?"; the kill form goes out three times and the object is forgotten). Rows are selectable
// like Nearby rows: a click or Enter emits `select`, and the form then edits that object. An
// object whose kill is going out cannot be selected and has no delete.
import { computed, nextTick, ref, watch } from "vue";
import TagMark from "@/components/TagMark.vue";
import CopyMenu from "@/components/CopyMenu.vue";
import IconButton from "@/components/IconButton.vue";
import ObjectForm from "@/components/ObjectForm.vue";
import ObjectsQru from "@/components/ObjectsQru.vue";
import SymbolIcon from "@/components/SymbolIcon.vue";
import TabHelp from "@/components/TabHelp.vue";
import { t } from "@/i18n";
import type { OwnObjectsView } from "@/composables/useOwnObjects";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useCopyMenu } from "@/composables/useCopyMenu";
import { useSure } from "@/composables/useSure";
import { useRadios } from "@/composables/useRadios";
import { HEARD_ON_RADIOS, radioTone, titled } from "@/lib/channels";
import { stateText } from "@/lib/ownobjects";
import { inForce } from "@/lib/sendon";
import type { PageRadio } from "@/lib/radios";
import { categoryLabel, groupName } from "@/lib/qrucategories";
import type { OwnObjectRow } from "@/protocol/protocol";

const props = defineProps<{ objects: ReadonlyMap<string, OwnObjectRow>; form: OwnObjectsView }>();
const emit = defineEmits<{ select: [name: string, multi?: boolean] }>();
const { now } = useDaemonContext();
/** Radio tags on rows show while several radios are on: the radios it goes out on now (its own
 * that are on; none if none is). */
const { severalSenders: several, senders: enabled, byId } = useRadios();
/** The radio tags per row, by object name: first two by name, then "+n" with the rest in the
 * hover; none with one radio on. */
const radioTags = computed(() => {
  const on = enabled.value.map((radio) => radio.id);
  return new Map(
    [...props.objects.values()].map((row) => {
      const radios = several.value ? inForce(row.radios, on).flatMap((id) => byId(id) ?? []) : [];
      return [row.name, { shown: radios.slice(0, HEARD_ON_RADIOS), rest: radios.slice(HEARD_ON_RADIOS) }];
    }),
  );
});
const NONE = { shown: [], rest: [] } as const;
const tagsOf = (row: OwnObjectRow): { readonly shown: readonly PageRadio[]; readonly rest: readonly PageRadio[] } => radioTags.value.get(row.name) ?? NONE;
/** The hover words of a radio's tag: "Sent on radio 20 m". */
const sentOn = (radio: PageRadio): string => t("objects.sent_on", { name: radio.name });
const sure = useSure<string>();
/** The copy menu of a row: the name of the object. */
const copy = useCopyMenu((item) => (item.dataset["name"] === undefined ? [] : [{ kind: "name", text: item.dataset["name"] }]));
const rows = computed(() =>
  [...props.objects.values()].sort((a, b) => (a.created_at === b.created_at ? a.name.localeCompare(b.name) : a.created_at < b.created_at ? -1 : 1)),
);
const scroller = ref<HTMLElement | null>(null);

/** A click, Enter or Space on a row (not on its buttons, whose Space is theirs): the form takes
 * the object and the map selects it; Ctrl (Cmd on a Mac) adds its card to the open ones. */
function select(event: MouseEvent | KeyboardEvent, row: OwnObjectRow): void {
  if (event instanceof KeyboardEvent && event.target !== event.currentTarget) return;
  if (event instanceof KeyboardEvent && event.key === " ") event.preventDefault();
  if (row.state !== "live") return;
  props.form.edit(row.name);
  emit("select", row.name, event.ctrlKey || event.metaKey);
}

// the selected object (here or from its card) goes into the form, which is scrolled into sight
watch(
  () => props.form.editing,
  (name) => {
    if (name !== null) void nextTick(() => scroller.value?.querySelector<HTMLElement>("form.composebar")?.scrollIntoView?.({ block: "nearest" }));
  },
);
</script>

<template>
  <div class="objectspane">
    <TabHelp :label="t('objects.about_label')" picture="object">
      <span class="info-line">{{ t("objects.about1") }}</span>
      <span class="info-line">{{ t("objects.about2") }}</span>
    </TabHelp>
    <div ref="scroller" class="objectlist">
      <ObjectForm :form="form" />
      <fieldset class="myobjects">
        <legend>
          {{ t("objects.mine") }} <span v-if="rows.length > 0" class="muted">{{ rows.length }}</span>
        </legend>
        <p v-if="rows.length === 0" class="empty">{{ t("objects.none") }}</p>
        <ul v-else class="board ownobjects" :aria-label="t('objects.list')">
          <li
            v-for="row in rows"
            :key="row.name"
            class="bulletin ownobject copysource"
            :class="{ killing: row.state === 'killing', selectable: row.state === 'live', selected: form.editing === row.name }"
            :tabindex="row.state === 'live' ? 0 : undefined"
            :aria-current="form.editing === row.name ? 'true' : undefined"
            :data-name="row.name"
            v-on="copy.on.value"
            @click="copy.unlessHeld(() => select($event, row))"
            @keydown.enter="select($event, row)"
            @keydown.space="select($event, row)"
          >
            <div v-if="row.state === 'live'" class="bulletin-actions" @click.stop>
              <IconButton
                kind="delete"
                class="bulletin-delete"
                :title="t('objects.delete_title')"
                :armed="sure.armed.value === row.name"
                :label="t('objects.delete_label', { kind: row.kind, name: row.name })"
                @click="sure.press(row.name, () => form.kill(row.name))"
              />
            </div>
            <div class="own-main">
              <p class="bulletin-head">
                <SymbolIcon :table="row.symbol_table" :code="row.symbol_code" :size="22" />
                <strong class="mono">{{ row.name }}</strong>
                <span class="muted"> {{ t("objects.kind_word", { kind: row.kind }) }}</span>
              </p>
              <p v-if="row.comment" class="bulletin-text">{{ row.comment }}</p>
              <p class="bulletin-meta muted">{{ stateText(row, now) }}</p>
            </div>
            <div class="own-tags" :class="{ several }">
              <TagMark v-if="row.qru_group" tone="neutral" class="own-category" :title="t('objects.in_group', { group: groupName(row.qru_group) })">{{
                categoryLabel(row.qru_group)
              }}</TagMark>
              <TagMark v-for="radio in tagsOf(row).shown" :key="radio.id" :tone="radioTone(radio)" class="own-radio" :title="sentOn(radio)">{{
                radio.name
              }}</TagMark>
              <TagMark v-if="tagsOf(row).rest.length > 0" tone="neutral" class="own-radio" :title="titled(tagsOf(row).rest.map(sentOn))"
                >{{ t("radio.more", { n: tagsOf(row).rest.length }) }}<span class="sr-only"> {{ titled(tagsOf(row).rest.map(sentOn)) }}</span></TagMark
              >
            </div>
          </li>
        </ul>
      </fieldset>
      <ObjectsQru />
    </div>
    <CopyMenu v-if="copy.menu.value" :key="copy.key.value" v-bind="copy.menu.value" @close="copy.close()" />
  </div>
</template>
