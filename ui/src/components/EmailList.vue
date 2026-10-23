<script setup lang="ts">
// The Email tab's list: every message to and from the gateway EMAIL-2 as a row (EmailRow), the newest first. Rows that came in after `freshAfter` (a message id) are the new ones.
import { computed } from "vue";
import EmailRow from "@/components/EmailRow.vue";
import { useNow } from "@/composables/useNow";
import { mailItems } from "@/lib/mailitems";
import type { MessageRow } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ thread: readonly MessageRow[]; freshAfter?: number; heardDirect?: ReadonlySet<string> }>(), {
  freshAfter: Number.MAX_SAFE_INTEGER,
  heardDirect: () => new Set<string>(),
});
const emit = defineEmits<{ retry: [id: number]; cancel: [id: number]; delete: [id: number] }>();
const now = useNow(30000);
const items = computed(() => mailItems(props.thread));
</script>

<template>
  <p v-if="items.length === 0" class="empty">No mail yet.</p>
  <ul v-else class="maillist" aria-label="Mail">
    <EmailRow
      v-for="item in items"
      :key="item.row.id"
      :item="item"
      :fresh="item.row.state === 'received' && item.row.id > freshAfter"
      :now="now"
      :heard-direct="heardDirect"
      @retry="emit('retry', $event)"
      @cancel="emit('cancel', $event)"
      @delete="emit('delete', $event)"
    />
  </ul>
</template>
