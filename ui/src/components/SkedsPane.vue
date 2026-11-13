<script setup lang="ts">
// The Skeds tab: the board of when stations will be on the air (the project's board on neo.oh2gba.eu, read by the daemon: the topic `skeds`), the nearest first. A row is a time, a dial and the calls that will be there: skeds with the same
// times and dial are one row (lib/skeds.ts). The time is written in UTC with how long until it ("in 3 h", "now" while it runs), and the viewer's own time is its title; the note is one line, the whole of it in the title. A row with a sked of ours
// has Delete (two presses, "sure?": it takes the sked off the board for everybody); any other row has Join, which posts a sked of ours with the same times and dial. The column of these two keeps its width in every row, and Join is off, not gone,
// while a post is not possible, so that nothing moves when that changes. A board that cannot be reached shows the skeds last read and says nothing; a closed board shows the skeds without the form. An (i) at the top (TabHelp) says that the board is public
// and not sent by radio. The form is fixed at the bottom of the tab (components/SkedCompose.vue), as the box of every tab.
import { computed } from "vue";
import IconButton from "@/components/IconButton.vue";
import SkedCompose from "@/components/SkedCompose.vue";
import TabHelp from "@/components/TabHelp.vue";
import TagMark from "@/components/TagMark.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useSure } from "@/composables/useSure";
import { t } from "@/i18n";
import { groups, hasCall, inText, localText, mayPostAs, noteOf, whenText, type SkedGroup } from "@/lib/skeds";

const { skeds, call, now, send } = useDaemonContext();
const sure = useSure<string>(); // (the key of a row)
const shown = computed(() => groups(skeds.value?.rows ?? [], now.value));
const state = computed(() => skeds.value?.state ?? null);
/** The empty board is said only where the board was read or is closed: a board that could not be reached is not "empty". */
const listed = computed(() => state.value === "ok" || state.value === "closed");
const canPost = computed(() => state.value === "ok" && mayPostAs(call.value));
const remove = (g: SkedGroup): void => g.ours.forEach((row) => void send({ cmd: "sked_delete", id: row.id }));
const join = (g: SkedGroup): boolean => send({ cmd: "sked_post", from: g.from, to: g.to, dial: g.dial, note: "" });
</script>

<template>
  <div class="boardwrap">
    <TabHelp :label="t('skeds.about_label')">
      <span class="info-line">{{ t("skeds.about1") }}</span>
      <span class="info-line">{{ t("skeds.about2") }}</span>
    </TabHelp>
    <div class="boardpane">
      <p v-if="shown.length === 0 && listed" class="empty">{{ t("skeds.empty") }}</p>
      <ul v-if="shown.length > 0" class="board">
        <li v-for="g in shown" :key="g.key" class="sked" :class="{ mine: g.ours.length > 0 }">
          <div class="sked-main">
            <p class="sked-when" :title="localText(g.from, g.to)">
              <strong>{{ whenText(g.from, g.to) }}</strong> <span class="muted">{{ inText(g.from, now) }}</span>
            </p>
            <p class="sked-line">
              <span class="mono sked-dial">{{ g.dial }}</span>
              <span v-for="r in g.rows" :key="r.id" class="sked-call">
                <strong class="mono">{{ r.call }}</strong>
                <TagMark v-if="r.ours" tone="outline">{{ t("skeds.ours") }}</TagMark>
              </span>
            </p>
            <p v-if="noteOf(g) !== ''" class="sked-note muted" :title="noteOf(g)">{{ noteOf(g) }}</p>
          </div>
          <div class="sked-actions">
            <IconButton
              v-if="g.ours.length > 0"
              kind="delete"
              :title="t('skeds.delete_title')"
              :armed="sure.armed.value === g.key"
              :label="t('skeds.delete_label', { when: whenText(g.from, g.to) })"
              @click="sure.press(g.key, () => remove(g))"
            />
            <button
              v-else-if="state !== 'closed' && !hasCall(g, call)"
              type="button"
              class="btn small"
              :disabled="!canPost"
              :title="t('skeds.join_title')"
              :aria-label="t('skeds.join_label', { calls: g.rows.map((r) => r.call).join(', '), when: whenText(g.from, g.to) })"
              @click="join(g)"
            >
              {{ t("skeds.join") }}
            </button>
          </div>
        </li>
      </ul>
    </div>
    <SkedCompose v-if="state !== 'closed'" />
  </div>
</template>
