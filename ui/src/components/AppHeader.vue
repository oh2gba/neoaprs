<script setup lang="ts">
// The one calm line at the top: the title, which is a link to the project's page (it looks like the title, not like a link: only a hover or the keyboard shows it), the amber button "no call set" while the call is empty (it opens the first-run guide: nothing is transmitted
// until a call is set), and, at the right, the number of messages not seen, a button that opens them (the Email tab when all of them are the gateway's). Our call is not here, nor the radio state, the version or the update: they are in the footer of the panel (PanelFooter).
import MessageGlyph from "@/components/MessageGlyph.vue";
import { t } from "@/i18n";
import { unreadText } from "@/lib/unread";

defineProps<{
  /** Our call from the settings; only an empty one matters here (the button), null while the daemon has not said. */
  call: string | null;
  unread: number;
}>();
const emit = defineEmits<{ messages: []; setup: [] }>();

/** The project's page. */
const PROJECT_URL = "https://oh2gba.github.io/neoaprs/";
</script>

<template>
  <header class="appheader">
    <h1>
      <a class="brand" :href="PROJECT_URL" target="_blank" rel="noopener" :title="t('header.project_title')">NeoAPRS</a>
    </h1>
    <button v-if="call === ''" type="button" class="nocall" :title="t('header.no_call_title')" @click="emit('setup')">
      {{ t("header.no_call") }}
    </button>
    <button v-if="unread > 0" type="button" class="badge headmail" :title="t('header.unread_open', { n: unread })" @click="emit('messages')">
      <MessageGlyph :size="14" /> {{ unread }}<span class="sr-only"> {{ unreadText(unread) }}</span>
    </button>
  </header>
</template>
