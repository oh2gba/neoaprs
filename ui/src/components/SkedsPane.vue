<script setup lang="ts">
// The Skeds tab: the board of when stations will be on the air (the project's board, read by the
// daemon: topic `skeds`), nearest first, and under it the past tests, newest first, in a section of
// the Bulletins tab's kind. Skeds with the same times and dial are one row (lib/skeds.ts, SkedItem).
// A row with a sked of ours has Delete (two presses); other rows have Join, which posts a sked with
// the same times and dial. That column keeps its width and Join is off, not gone, while a post is not
// possible. A past test has the trash there (two presses), which takes it off this installation's
// list only (`sked_past_delete`). The past tests are the last thing of the scrolling pane, so
// nothing moves when they come or change. An unreachable board shows the skeds and past tests last
// read; a closed board shows them without the form. The form is fixed at the bottom (SkedCompose),
// and under it the chat (ChatBox).
import { computed } from "vue";
import IconButton from "@/components/IconButton.vue";
import ChatBox from "@/components/ChatBox.vue";
import SkedCompose from "@/components/SkedCompose.vue";
import SkedItem from "@/components/SkedItem.vue";
import TabHelp from "@/components/TabHelp.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useCommandInFlight } from "@/composables/useInFlight";
import { useSure } from "@/composables/useSure";
import { t } from "@/i18n";
import { groups, hasCall, mayPostAs, pastGroups, whenText, type SkedGroup } from "@/lib/skeds";

const { skeds, call, now, send } = useDaemonContext();
const sure = useSure<string>();
const shown = computed(() => groups(skeds.value?.rows ?? [], now.value));
const past = computed(() => pastGroups(skeds.value?.past ?? [], skeds.value?.rows ?? [], now.value));
const state = computed(() => skeds.value?.state ?? null);
/**
 * The empty board is said only where the board was read or is closed: an unreachable board is not
 * "empty".
 */
const listed = computed(() => state.value === "ok" || state.value === "closed");
const canPost = computed(() => state.value === "ok" && mayPostAs(call.value));
const remove = (g: SkedGroup): void => g.ours.forEach((row) => void send({ cmd: "sked_delete", id: row.id }));
const pastKey = (g: SkedGroup): string => `past:${g.key}`;
const removePast = (g: SkedGroup): void => void send({ cmd: "sked_past_delete", ids: g.rows.map((row) => row.id) });
const joining = useCommandInFlight("sked_post", () => skeds.value?.rows);
const join = (g: SkedGroup): boolean =>
  joining.run(() => send({ cmd: "sked_post", from: g.from, to: g.to, dial: g.dial, note: "" }));
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
        <SkedItem v-for="g in shown" :key="g.key" :group="g" :now="now">
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
            :disabled="!canPost || joining.busy.value"
            :title="t('skeds.join_title')"
            :aria-label="
              t('skeds.join_label', { calls: g.rows.map((r) => r.call).join(', '), when: whenText(g.from, g.to) })
            "
            @click="join(g)"
          >
            {{ t("skeds.join") }}
          </button>
        </SkedItem>
      </ul>
      <fieldset v-if="listed || past.length > 0" class="board-section sked-past" :aria-label="t('skeds.past_title')">
        <legend class="board-title">{{ t("skeds.past_title") }}</legend>
        <p v-if="past.length === 0" class="empty">{{ t("skeds.past_empty") }}</p>
        <ul v-else class="board">
          <SkedItem v-for="g in past" :key="g.key" :group="g">
            <IconButton
              kind="delete"
              :armed="sure.armed.value === pastKey(g)"
              :label="t('skeds.past_delete_label', { when: whenText(g.from, g.to) })"
              @click="sure.press(pastKey(g), () => removePast(g))"
            />
          </SkedItem>
        </ul>
      </fieldset>
    </div>
    <SkedCompose v-if="state !== 'closed'" />
    <ChatBox />
  </div>
</template>
