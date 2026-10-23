<script setup lang="ts">
// The Email tab's list: every message to and from the gateway EMAIL-2 as a row (EmailRow), the oldest first and scrolled to the newest at the bottom, as the Messages tab is, so that the newest mail is next to the box to write in under it. It fills the
// height the tab leaves it and scrolls. Rows that came in after `freshAfter` (a message id) are the new ones.
import { computed, ref } from "vue";
import EmailRow from "@/components/EmailRow.vue";
import { useNow } from "@/composables/useNow";
import { useToNewest } from "@/composables/useToNewest";
import { t } from "@/i18n";
import { mailItems } from "@/lib/mailitems";
import type { MessageRow } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ thread: readonly MessageRow[]; freshAfter?: number; heardDirect?: ReadonlySet<string> }>(), {
  freshAfter: Number.MAX_SAFE_INTEGER,
  heardDirect: () => new Set<string>(),
});
const emit = defineEmits<{ retry: [id: number]; cancel: [id: number]; delete: [id: number] }>();
const now = useNow(30000);
const items = computed(() => mailItems(props.thread));
const log = ref<HTMLElement | null>(null);
useToNewest(log, () => props.thread.length);
</script>

<template>
  <div ref="log" class="maillist-wrap">
    <p v-if="items.length === 0" class="empty">{{ t("email.none") }}</p>
    <ul v-else class="maillist" :aria-label="t('email.list')">
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
  </div>
</template>
