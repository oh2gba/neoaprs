<script setup lang="ts">
// The Objects tab, three group boxes one under the other (an (i) at the top, TabHelp, says what an object is), the tab scrolling as a whole: **Add an object** first, so that it is always within reach (components/ObjectForm.vue, always there;
// "Edit NAME" while an object is being changed), **My objects**, the objects and items of ours, oldest first, each with its symbol, its name, what kind it is, its category as a tag in a column of its own, how often it was sent and when it goes out next
// (or that it is sent only when asked) and its comment; the delete button at its corner kills it (two presses, the second after "sure?": the killed form goes out three times and it is forgotten); and **Local info** last, where QRU is asked (components/ObjectsQru.vue),
// as the form's category is what offers an object to those who ask. The rows are selectable like the rows of the Nearby tab (a click or Enter highlights the row and says `select`, which selects the object on the map as a click there does), and the
// form changes the selected object: Save; with none selected it adds a new object: Add; selecting a row scrolls the tab up to the form. An object whose kill is going out is not selectable and has no delete.
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
import { stateText } from "@/lib/ownobjects";
import { categoryLabel, groupName } from "@/lib/qrucategories";
import type { OwnObjectRow } from "@/protocol/protocol";

const props = defineProps<{ objects: ReadonlyMap<string, OwnObjectRow>; form: OwnObjectsView }>();
const emit = defineEmits<{ select: [name: string, multi?: boolean] }>();
const { fallbackPath, now } = useDaemonContext();
const sure = useSure<string>(); // (the name of a row)
/** The copy menu of a row: the name of the object. */
const copy = useCopyMenu((item) => (item.dataset["name"] === undefined ? [] : [{ kind: "name", text: item.dataset["name"] }]));
const rows = computed(() =>
  [...props.objects.values()].sort((a, b) => (a.created_at === b.created_at ? a.name.localeCompare(b.name) : a.created_at < b.created_at ? -1 : 1)),
);
const scroller = ref<HTMLElement | null>(null);

/** A click or Enter on a row (not on the buttons in it): the form takes the object, and the map selects it; with Ctrl (Cmd on a Mac) its card is added to the open ones. */
function select(event: MouseEvent | KeyboardEvent, row: OwnObjectRow): void {
  if (row.state !== "live" || (event instanceof KeyboardEvent && event.target !== event.currentTarget)) return;
  props.form.edit(row.name);
  emit("select", row.name, event.ctrlKey || event.metaKey);
}

// the object that is selected (here, or from its card) is in the form, which is brought into sight
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
      <ObjectForm :form="form" :fallback-path="fallbackPath" />
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
            <div class="own-main">
              <p class="bulletin-head">
                <SymbolIcon :table="row.symbol_table" :code="row.symbol_code" :size="22" />
                <strong class="mono">{{ row.name }}</strong>
                <span class="muted"> {{ t("objects.kind_word", { kind: row.kind }) }}</span>
              </p>
              <p v-if="row.comment" class="bulletin-text">{{ row.comment }}</p>
              <p class="bulletin-meta muted">{{ stateText(row, now) }}</p>
            </div>
            <div class="own-tags">
              <TagMark v-if="row.qru_group" tone="neutral" class="own-category" :title="t('objects.in_group', { group: groupName(row.qru_group) })">{{
                categoryLabel(row.qru_group)
              }}</TagMark>
            </div>
          </li>
        </ul>
      </fieldset>
      <ObjectsQru />
    </div>
    <CopyMenu v-if="copy.menu.value" :key="copy.key.value" v-bind="copy.menu.value" @close="copy.close()" />
  </div>
</template>
