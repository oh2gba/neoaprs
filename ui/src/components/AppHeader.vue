<script setup lang="ts">
// The one calm line at the top: the title, which is a link to the project's page (it looks like the title, not like a link: only a hover or the keyboard shows it), the amber button "no call set" while the call is empty (it opens the first-run guide: nothing is transmitted
// until a call is set), the marks that say how things stand at the right (Daemon in a browser, Radio, RX only, Beacon off, Internet, GPS: lib/pills.ts, each a button that opens the place where it is set, with a hover title that says what it means; the Daemon mark has nothing to open), and the number of messages not seen, a button that opens them (the Email tab when all of them are the gateway's).
// The Map mark says how far the download of the detailed map is. Our call is not here, nor the version: the call is in the Settings tab, the version in Settings → Update check. A newer version is the first mark, Update, which opens Settings → New version.
import TagMark from "@/components/TagMark.vue";
import MessageGlyph from "@/components/MessageGlyph.vue";
import { t } from "@/i18n";
import type { HeaderPill, PillTarget } from "@/lib/pills";
import { unreadText } from "@/lib/unread";

defineProps<{
  /** Our call from the settings; only an empty one matters here (the button), null while the daemon has not said. */
  call: string | null;
  unread: number;
  /** The marks before the count (Update, Daemon, Radio, RX only, Beacon off, GPS, Internet). */
  pills?: readonly HeaderPill[];
}>();
const emit = defineEmits<{ messages: []; setup: []; open: [target: PillTarget, focus: string] }>();

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
        :as="pill.target === null ? 'span' : 'button'"
        :tone="pill.tone"
        :class="['headpill', `pill-${pill.id}`, { rxonly: pill.id === 'rx' }]"
        :title="t(pill.title, pill.titleValues)"
        :role="pill.target === null ? 'status' : undefined"
        @click="pill.target !== null && emit('open', pill.target, pill.focus)"
        >{{ t(pill.text, pill.textValues) }}</TagMark
      >
    </span>
    <TagMark v-if="unread > 0" as="button" class="badge headmail" :title="t('header.unread_open', { n: unread })" @click="emit('messages')">
      <MessageGlyph :size="14" /> {{ unread }}<span class="sr-only"> {{ unreadText(unread) }}</span>
    </TagMark>
  </header>
</template>
