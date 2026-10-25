<script setup lang="ts">
// The Objects tab: the objects and items of ours, oldest first, each with its symbol, its name, what kind it is, its QRU group if it has one, how often it was sent and when it goes out next (or that it is sent only when asked), and its comment; Edit opens the form with
// what the daemon has of it, and the delete button at its corner kills it (two presses, the second after "sure?": the killed form goes out three times and it is forgotten). An object whose kill is going out has
// neither. New opens the form for a new object at the place we are (components/ObjectForm.vue), in the box at the bottom of the tab; the list fills the tab above it and is scrolled to the newest.
import { computed, nextTick, ref, watch } from "vue";
import IconButton from "@/components/IconButton.vue";
import ObjectForm from "@/components/ObjectForm.vue";
import SymbolIcon from "@/components/SymbolIcon.vue";
import { t } from "@/i18n";
import type { OwnObjectsView } from "@/composables/useOwnObjects";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useSure } from "@/composables/useSure";
import { useToNewest } from "@/composables/useToNewest";
import { stateText } from "@/lib/ownobjects";
import type { OwnObjectRow } from "@/protocol/protocol";

const props = defineProps<{ objects: ReadonlyMap<string, OwnObjectRow>; form: OwnObjectsView }>();
const { fallbackPath, now } = useDaemonContext();
const sure = useSure<string>(); // (the name of a row)
const rows = computed(() =>
  [...props.objects.values()].sort((a, b) => (a.created_at === b.created_at ? a.name.localeCompare(b.name) : a.created_at < b.created_at ? -1 : 1)),
);
const log = ref<HTMLElement | null>(null);
const toNewest = useToNewest(log, () => rows.value.length);
// the form opening or closing changes the height of the list: the newest object stays in sight
watch(
  () => props.form.open,
  () => void nextTick(toNewest),
);
</script>

<template>
  <div class="objectspane">
    <div class="toolbar">
      <button class="btn primary" type="button" @click="form.start()">{{ t("objects.new") }}</button>
    </div>
    <div ref="log" class="objectlist">
      <p v-if="rows.length === 0 && !form.open" class="empty">{{ t("objects.none") }}</p>
      <ul class="board ownobjects">
        <li v-for="row in rows" :key="row.name" class="bulletin ownobject" :class="{ killing: row.state === 'killing' }">
          <div v-if="row.state === 'live'" class="bulletin-actions">
            <button type="button" class="btn object-edit" :aria-label="t('objects.edit_label', { name: row.name })" @click="form.edit(row.name)">
              {{ t("objects.edit") }}
            </button>
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
            <span v-if="row.qru_group" class="muted mono"> {{ t("objects.in_group", { group: row.qru_group }) }}</span>
          </p>
          <p v-if="row.comment" class="bulletin-text">{{ row.comment }}</p>
          <p class="bulletin-meta muted">{{ stateText(row, now) }}</p>
        </li>
      </ul>
    </div>
    <ObjectForm v-if="form.open" :form="form" :fallback-path="fallbackPath" />
  </div>
</template>
