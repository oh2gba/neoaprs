<script setup lang="ts">
// The one calm line at the top: the title, which is a link to the project's page (it looks like the title, not like a link: only a hover or the keyboard shows it), the amber button "no call set" while the call is empty (it opens the first-run guide: nothing is transmitted
// until a call is set), the marks that say what is out of the ordinary at the right (RX only, Beacon off, Internet, GPS: lib/pills.ts, each a button that opens the place where it is set, with a hover title that says what it means), and the number of messages not seen, a button that opens them (the Email tab when all of them are the gateway's). Our call is not here, nor the radio state or the version: they are in the footer of the panel (PanelFooter).
// A phone, whose map has no footer, has the newer version here too (`update`): a small badge that opens the dialog of the update.
import TagMark from "@/components/TagMark.vue";
import MessageGlyph from "@/components/MessageGlyph.vue";
import { t } from "@/i18n";
import type { HeaderPill, PillTarget } from "@/lib/pills";
import { unreadText } from "@/lib/unread";

defineProps<{
  /** Our call from the settings; only an empty one matters here (the button), null while the daemon has not said. */
  call: string | null;
  unread: number;
  /** The newer version, where the header shows it (a phone); null for none. */
  update?: string | null;
  /** The marks before the count (RX only, Beacon off, Internet, GPS). */
  pills?: readonly HeaderPill[];
}>();
const emit = defineEmits<{ messages: []; setup: []; update: []; open: [target: PillTarget] }>();

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
    <span v-if="pills?.length" class="headpills">
      <TagMark
        v-for="pill in pills"
        :key="pill.id"
        as="button"
        :tone="pill.tone"
        :class="['headpill', `pill-${pill.id}`, { rxonly: pill.id === 'rx' }]"
        :title="t(pill.title)"
        @click="emit('open', pill.target)"
        >{{ t(pill.text) }}</TagMark
      >
    </span>
    <TagMark v-if="update" as="button" class="badge headupdate" :title="t('help.update.title', { version: update })" @click="emit('update')">
      <span aria-hidden="true">&#8679;</span> {{ update }}<span class="sr-only"> {{ t("help.update.title", { version: update }) }}</span>
    </TagMark>
    <TagMark v-if="unread > 0" as="button" class="badge headmail" :title="t('header.unread_open', { n: unread })" @click="emit('messages')">
      <MessageGlyph :size="14" /> {{ unread }}<span class="sr-only"> {{ unreadText(unread) }}</span>
    </TagMark>
  </header>
</template>
