<script setup lang="ts">
// The menu of a row of the Stations table: Message and the four directed queries (Ask for position, Ask for status, Ask what it hears direct, Trace the route) where the card has Message, then Show on map (or its card, for a station with no position), "Alert me when…" (a station
// that is not ours: the parent opens the choice, StationAlertBox), Copy call and the QRZ page, then Forget
// (asking twice, as the trash can of the row does: the first press says "Really forget?", the second forgets). Under the queries a short muted line says that many stations do not answer them. It opens where the pointer is (a right-click or a long press) or under the "..." button, is kept inside the window,
// takes the focus on its first item, is moved in by Up, Down, Home and End, and closed by Esc (the focus goes back to `trigger`), a press outside it, Tab, or an item that was chosen (useContextMenu). The row it is for is `row`; an item is said to the page with one event, the parent does it.
import { useReceiveOnly } from "@/composables/useReceiveOnly";
import { rxOnlyReason } from "@/lib/compose";
import { computed, ref } from "vue";
import { useContextMenu } from "@/composables/useContextMenu";
import { t } from "@/i18n";
import { qrzUrl } from "@/lib/calls";
import { hasPosition, menuGroup, menuItems, QUERY_KINDS, type MenuItem, type QueryKind } from "@/lib/stations";
import type { StationRow } from "@/protocol/protocol";

const props = defineProps<{ row: StationRow; x: number; y: number; trigger: HTMLElement | null; armed: boolean }>();
const emit = defineEmits<{
  close: [];
  message: [call: string];
  ask: [call: string, kind: QueryKind];
  show: [call: string];
  alert: [call: string];
  copy: [call: string];
  forget: [call: string];
}>();

const list = ref<HTMLElement | null>(null);
const buttons = ref<HTMLElement[]>([]);

const rxOnly = useReceiveOnly();
const items = computed(() => menuItems(props.row));
const qrz = computed(() => qrzUrl(props.row.call));
const asks = computed(() => items.value.some((item) => item.startsWith("ask_")));
/** The items with a line above where a group begins, and the muted line after the last of the queries. */
const entries = computed(() =>
  items.value.map((item, index) => ({
    item,
    line: index > 0 && menuGroup(item) !== menuGroup(items.value[index - 1] ?? item),
    note: item === "ask_trace",
  })),
);
const menu = useContextMenu({ x: () => props.x, y: () => props.y, trigger: () => props.trigger, list, buttons, close: () => emit("close") });

function label(item: MenuItem): string {
  switch (item) {
    case "message":
      return t("station.card.message");
    case "ask_position":
      return t("station.menu.ask_position");
    case "ask_status":
      return t("station.menu.ask_status");
    case "ask_heard":
      return t("station.menu.ask_heard");
    case "ask_trace":
      return t("station.menu.ask_trace");
    case "show":
      return hasPosition(props.row) ? t("station.menu.show_map") : t("station.menu.show_card");
    case "alert":
      return t("station.menu.alert");
    case "copy":
      return t("station.menu.copy");
    case "qrz":
      return t("station.menu.qrz");
    case "forget":
      return props.armed ? t("station.menu.forget_sure") : t("station.menu.forget");
  }
}

/** The item does its work and the menu closes, except Forget the first time (it asks again); the QRZ page is a link, which opens in a tab of its own. */
function choose(item: MenuItem): void {
  const call = props.row.call;
  if (item === "forget") {
    emit("forget", call);
    if (!props.armed) return;
  } else if (item === "message") emit("message", call);
  else if (item === "show") emit("show", call);
  else if (item === "alert") emit("alert", call);
  else if (item === "copy") emit("copy", call);
  else if (item !== "qrz") emit("ask", call, QUERY_KINDS.find((kind) => `ask_${kind}` === item) ?? "status");
  menu.done();
}
</script>

<template>
  <ul
    ref="list"
    class="ctxmenu"
    role="menu"
    :aria-label="t('station.menu.label', { call: row.call })"
    :style="{ left: `${menu.at.value.left}px`, top: `${menu.at.value.top}px` }"
    @keydown="menu.onKey"
    @contextmenu.prevent
  >
    <template v-for="({ item, line, note }, index) in entries" :key="item">
      <li v-if="line" class="ctxmenu-line" role="separator"></li>
      <li role="none">
        <a
          v-if="item === 'qrz' && qrz"
          :ref="(el) => (buttons[index] = el as HTMLElement)"
          class="ctxmenu-item"
          role="menuitem"
          tabindex="-1"
          :href="qrz"
          target="_blank"
          rel="noopener noreferrer"
          :data-item="item"
          @click="menu.done()"
        >
          {{ label(item) }}
        </a>
        <button
          v-else
          :ref="(el) => (buttons[index] = el as HTMLElement)"
          type="button"
          role="menuitem"
          class="ctxmenu-item"
          :class="{ armed: item === 'forget' && armed, danger: item === 'forget' }"
          :disabled="rxOnly && item.startsWith('ask_')"
          :title="rxOnly && item.startsWith('ask_') ? rxOnlyReason() : undefined"
          tabindex="-1"
          :data-item="item"
          @click="choose(item)"
        >
          {{ label(item) }}
        </button>
      </li>
      <li v-if="note && asks" class="ctxmenu-note muted" role="none">{{ t("station.menu.note") }}</li>
    </template>
  </ul>
</template>
