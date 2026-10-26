<script setup lang="ts">
// The count on a tab (the row of tabs and the menu of them both have it): the messages not seen, the new bulletins; nothing for none. Its title says what is counted (lib/unread.ts).
import TagMark from "@/components/TagMark.vue";
import type { TabId } from "@/lib/layout";
import { badgeText } from "@/lib/unread";

defineProps<{ tab: TabId; count?: number }>();
</script>

<template>
  <TagMark v-if="count" class="badge" :title="badgeText(tab, count)">{{ count }}</TagMark>
</template>
