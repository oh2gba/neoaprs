<script setup lang="ts">
// The Objects tab: the objects and items of ours, oldest first, each with its symbol, its name, what kind it is, how often it was sent and when it goes out next, and its comment; Edit opens the form with
// what the daemon has of it, and the delete button at its corner kills it (two presses, the second after "sure?": the killed form goes out three times and it is forgotten). An object whose kill is going out has
// neither. New opens the form for a new object at the place we are (components/ObjectForm.vue).
import { computed } from "vue";
import IconButton from "@/components/IconButton.vue";
import ObjectForm from "@/components/ObjectForm.vue";
import SymbolIcon from "@/components/SymbolIcon.vue";
import type { OwnObjectsView } from "@/composables/useOwnObjects";
import { useSure } from "@/composables/useSure";
import { stateText } from "@/lib/ownobjects";
import type { OwnObjectRow } from "@/protocol/protocol";

const props = defineProps<{ objects: ReadonlyMap<string, OwnObjectRow>; form: OwnObjectsView; fallbackPath: string; now: number }>();
const sure = useSure<string>(); // (the name of a row)
const rows = computed(() =>
  [...props.objects.values()].sort((a, b) => (a.created_at === b.created_at ? a.name.localeCompare(b.name) : a.created_at < b.created_at ? -1 : 1)),
);
</script>

<template>
  <div class="objectspane">
    <div class="toolbar">
      <button class="btn primary" type="button" @click="form.start()">New</button>
    </div>
    <ObjectForm v-if="form.open" :form="form" :fallback-path="fallbackPath" />
    <p v-if="rows.length === 0 && !form.open" class="empty">No objects.</p>
    <ul class="board ownobjects">
      <li v-for="row in rows" :key="row.name" class="bulletin ownobject" :class="{ killing: row.state === 'killing' }">
        <div v-if="row.state === 'live'" class="bulletin-actions">
          <button type="button" class="btn object-edit" :aria-label="`Edit ${row.name}`" @click="form.edit(row.name)">Edit</button>
          <IconButton
            kind="delete"
            class="bulletin-delete"
            title="Delete (kill on the air)"
            :armed="sure.armed.value === row.name"
            :label="`Delete the ${row.kind} ${row.name}`"
            @click="sure.press(row.name, () => form.kill(row.name))"
          />
        </div>
        <p class="bulletin-head">
          <SymbolIcon :table="row.symbol_table" :code="row.symbol_code" :size="22" />
          <strong class="mono">{{ row.name }}</strong>
          <span class="muted"> {{ row.kind }}</span>
        </p>
        <p v-if="row.comment" class="bulletin-text">{{ row.comment }}</p>
        <p class="bulletin-meta muted">{{ stateText(row, now) }}</p>
      </li>
    </ul>
  </div>
</template>
