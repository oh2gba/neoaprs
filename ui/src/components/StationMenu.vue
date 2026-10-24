<script setup lang="ts">
// The menu of a row of the Stations table: Message and the four directed queries (Ask for position, Ask for status, Ask what it hears direct, Trace the route) where the card has Message, then Show on map (or its card, for a station with no position), Copy call and the QRZ page, then Forget
// (asking twice, as the trash can of the row does: the first press says "Really forget?", the second forgets). Under the queries a short muted line says that many stations do not answer them. It opens where the pointer is (a right-click or a long press) or under the "..." button, is kept inside the window,
// takes the focus on its first item, is moved in by Up, Down, Home and End, and closed by Esc (the focus goes back to `trigger`), a press outside it, Tab, or an item that was chosen. The row it is for is `row`; an item is said to the page with one event, the parent does it.
import { computed, nextTick, onMounted, ref } from "vue";
import { usePopup } from "@/composables/usePopup";
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
  copy: [call: string];
  forget: [call: string];
}>();

const MARGIN = 8;
const open = ref(false);
const list = ref<HTMLElement | null>(null);
const buttons = ref<HTMLElement[]>([]);
const at = ref({ left: props.x, top: props.y });

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
    case "copy":
      return t("station.menu.copy");
    case "qrz":
      return t("station.menu.qrz");
    case "forget":
      return props.armed ? t("station.menu.forget_sure") : t("station.menu.forget");
  }
}

function close(): void {
  open.value = false;
  emit("close");
}
const popup = usePopup({ open, root: list, trigger: computed(() => props.trigger), close, focusAway: false, stopEscape: true });

/** The item does its work and the menu closes, except Forget the first time (it asks again); the QRZ page is a link, which opens in a tab of its own. */
function choose(item: MenuItem): void {
  const call = props.row.call;
  if (item === "forget") {
    emit("forget", call);
    if (!props.armed) return;
  } else if (item === "message") emit("message", call);
  else if (item === "show") emit("show", call);
  else if (item === "copy") emit("copy", call);
  else if (item !== "qrz") emit("ask", call, QUERY_KINDS.find((kind) => `ask_${kind}` === item) ?? "status");
  open.value = false;
  emit("close");
}

function focusItem(index: number): void {
  buttons.value[(index + buttons.value.length) % buttons.value.length]?.focus();
}
function onKey(event: KeyboardEvent): void {
  const now = buttons.value.findIndex((b) => b === document.activeElement);
  const step: Record<string, () => void> = {
    ArrowDown: () => focusItem(now + 1),
    ArrowUp: () => focusItem(now < 0 ? -1 : now - 1),
    Home: () => focusItem(0),
    End: () => focusItem(-1),
  };
  if (event.key === "Escape") {
    event.preventDefault();
    popup.onEscape(event);
  } else if (event.key === "Tab") {
    close();
  } else if (step[event.key]) {
    event.preventDefault();
    step[event.key]?.();
  }
}

/** Keeps the menu inside the window: where it was asked for, moved left and up as far as it needs. */
function clamp(): void {
  const box = list.value?.getBoundingClientRect();
  if (!box) return;
  const left = Math.max(MARGIN, Math.min(props.x, window.innerWidth - box.width - MARGIN));
  const top = Math.max(MARGIN, Math.min(props.y, window.innerHeight - box.height - MARGIN));
  at.value = { left, top };
}

onMounted(async () => {
  open.value = true;
  await nextTick();
  clamp();
  focusItem(0);
});
</script>

<template>
  <ul
    ref="list"
    class="ctxmenu"
    role="menu"
    :aria-label="t('station.menu.label', { call: row.call })"
    :style="{ left: `${at.left}px`, top: `${at.top}px` }"
    @keydown="onKey"
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
          @click="close"
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
