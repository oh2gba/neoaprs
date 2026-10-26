<script setup lang="ts">
// The Objects tab: the objects and items of ours, oldest first, each with its symbol, its name, what kind it is, its QRU group if it has one, how often it was sent and when it goes out next (or that it is sent only when asked), and its comment; the delete button
// at its corner kills it (two presses, the second after "sure?": the killed form goes out three times and it is forgotten). The rows are selectable like the rows of the Nearby tab (a click or Enter highlights the row and says `select`, which selects the object on the map as
// a click there does), and the form under the list (components/ObjectForm.vue, always there) changes the selected object: Save; with none selected it adds a new object: Add. An object whose kill is going out is not selectable and has no delete. The list fills the tab above
// the form and is scrolled to the end (an (i) at the top, TabHelp, says what an object is); the group box under the objects in it is Local info (QRU), where QRU is asked (ObjectsQru.vue), as the form's QRU group is what offers an object to those who ask; it scrolls on its own and the form keeps its height (its fields scroll), so that on a phone both are within reach.
import { computed, nextTick, ref, watch } from "vue";
import IconButton from "@/components/IconButton.vue";
import ObjectForm from "@/components/ObjectForm.vue";
import ObjectsQru from "@/components/ObjectsQru.vue";
import SymbolIcon from "@/components/SymbolIcon.vue";
import TabHelp from "@/components/TabHelp.vue";
import { t } from "@/i18n";
import type { OwnObjectsView } from "@/composables/useOwnObjects";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useSure } from "@/composables/useSure";
import { useToNewest } from "@/composables/useToNewest";
import { stateText } from "@/lib/ownobjects";
import { categoryLabel } from "@/lib/qrucategories";
import type { OwnObjectRow } from "@/protocol/protocol";

const props = defineProps<{ objects: ReadonlyMap<string, OwnObjectRow>; form: OwnObjectsView }>();
const emit = defineEmits<{ select: [name: string, multi?: boolean] }>();
const { fallbackPath, now } = useDaemonContext();
const sure = useSure<string>(); // (the name of a row)
const rows = computed(() =>
  [...props.objects.values()].sort((a, b) => (a.created_at === b.created_at ? a.name.localeCompare(b.name) : a.created_at < b.created_at ? -1 : 1)),
);
const log = ref<HTMLElement | null>(null);
useToNewest(log, () => rows.value.length);

/** A click or Enter on a row (not on the buttons in it): the form takes the object, and the map selects it; with Ctrl (Cmd on a Mac) its card is added to the open ones. */
function select(event: MouseEvent | KeyboardEvent, row: OwnObjectRow): void {
  if (row.state !== "live" || (event instanceof KeyboardEvent && event.target !== event.currentTarget)) return;
  props.form.edit(row.name);
  emit("select", row.name, event.ctrlKey || event.metaKey);
}

// the object that is selected (here, or from its card) is in sight
watch(
  () => props.form.editing,
  (name) => {
    if (name !== null) void nextTick(() => log.value?.querySelector<HTMLElement>("[aria-current='true']")?.scrollIntoView?.({ block: "nearest" }));
  },
);
</script>

<template>
  <div class="objectspane">
    <TabHelp :label="t('objects.about_label')" picture="object">
      <span class="info-line">{{ t("objects.about1") }}</span>
      <span class="info-line">{{ t("objects.about2") }}</span>
    </TabHelp>
    <div ref="log" class="objectlist">
      <p v-if="rows.length === 0" class="empty">{{ t("objects.none") }}</p>
      <ul class="board ownobjects" :aria-label="t('objects.list')">
        <li
          v-for="row in rows"
          :key="row.name"
          class="bulletin ownobject"
          :class="{ killing: row.state === 'killing', selectable: row.state === 'live', selected: form.editing === row.name }"
          :tabindex="row.state === 'live' ? 0 : undefined"
          :aria-current="form.editing === row.name ? 'true' : undefined"
          :data-name="row.name"
          @click="select($event, row)"
          @keydown.enter="select($event, row)"
          @keydown.space.prevent="select($event, row)"
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
          <p class="bulletin-head">
            <SymbolIcon :table="row.symbol_table" :code="row.symbol_code" :size="22" />
            <strong class="mono">{{ row.name }}</strong>
            <span class="muted"> {{ t("objects.kind_word", { kind: row.kind }) }}</span>
            <span v-if="row.qru_group" class="muted"> {{ t("objects.in_group", { group: categoryLabel(row.qru_group) }) }}</span>
          </p>
          <p v-if="row.comment" class="bulletin-text">{{ row.comment }}</p>
          <p class="bulletin-meta muted">{{ stateText(row, now) }}</p>
        </li>
      </ul>
      <ObjectsQru />
    </div>
    <ObjectForm :form="form" :fallback-path="fallbackPath" />
  </div>
</template>
