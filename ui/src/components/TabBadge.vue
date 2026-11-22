<script setup lang="ts">
// The count on a tab (row and menu): unseen messages, new bulletins; nothing for none. Its
// title says what is counted (lib/unread.ts).
import TagMark from "@/components/TagMark.vue";
import type { TabId } from "@/lib/layout";
import { badgeText } from "@/lib/unread";

defineProps<{ tab: TabId; count?: number }>();
</script>

<template>
  <TagMark v-if="count" class="badge" :title="badgeText(tab, count)">{{ count }}</TagMark>
</template>
