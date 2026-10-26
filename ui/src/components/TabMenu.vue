<script setup lang="ts">
// The tabs that do not fit in the row of the panel (SidePanel measures that), under one "More" button at the end of the row: it carries the count of everything that has a badge among them (the messages and the mail not seen, the new bulletins) when there is any.
// It opens a menu of those tabs in their order, each with its badge; a click on one picks it and closes the menu (the tab then takes its place in the row, so the open tab is never under More), Esc and a click outside close it, Up and Down, Home and End move in it
// (Down on the button opens it on the first, Up on the last).
import TagMark from "@/components/TagMark.vue";
import { computed, nextTick, ref } from "vue";
import TabBadge from "@/components/TabBadge.vue";
import { usePopup } from "@/composables/usePopup";
import { t } from "@/i18n";
import { tabTitle, type TabId } from "@/lib/layout";

const props = defineProps<{ tabs: readonly TabId[]; badges: Partial<Record<TabId, number>> }>();
const emit = defineEmits<{ pick: [tab: TabId] }>();

const open = ref(false);
const root = ref<HTMLElement | null>(null);
const button = ref<HTMLElement | null>(null);
const items = ref<HTMLElement[]>([]);
const total = computed(() => props.tabs.reduce((sum, id) => sum + (props.badges[id] ?? 0), 0));

function focusItem(index: number): void {
  const count = props.tabs.length;
  items.value[(index + count) % count]?.focus();
}
async function show(index: number): Promise<void> {
  open.value = true;
  await nextTick();
  focusItem(index);
}
function close(refocus: boolean): void {
  open.value = false;
  items.value = [];
  if (refocus) button.value?.focus();
}
function toggle(): void {
  if (open.value) close(false);
  else open.value = true;
}
function pick(id: TabId): void {
  emit("pick", id);
  close(true);
}
function buttonKey(event: KeyboardEvent): void {
  if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
  event.preventDefault();
  void show(event.key === "ArrowDown" ? 0 : props.tabs.length - 1);
}
const popup = usePopup({ open, root, trigger: button, close: () => close(false), focusAway: false, stopEscape: true });
function menuKey(event: KeyboardEvent): void {
  const at = items.value.findIndex((item) => item === document.activeElement);
  const step: Record<string, () => void> = {
    ArrowDown: () => focusItem(at + 1),
    ArrowUp: () => focusItem(at - 1),
    Home: () => focusItem(0),
    End: () => focusItem(props.tabs.length - 1),
  };
  if (event.key === "Escape") {
    event.preventDefault();
    popup.onEscape(event);
  } else if (event.key === "Tab") {
    close(false);
  } else if (step[event.key]) {
    event.preventDefault();
    step[event.key]?.();
  }
}
</script>

<template>
  <div ref="root" class="tabmenu">
    <button
      id="tabmenu-button"
      ref="button"
      type="button"
      class="tab tabmenu-button"
      aria-haspopup="menu"
      :aria-expanded="open"
      aria-controls="tabmenu-list"
      @click="toggle"
      @keydown="buttonKey"
    >
      {{ t("tab.more") }} <span aria-hidden="true">&#9662;</span>
      <TagMark v-if="total > 0" class="badge" aria-hidden="true">{{ total }}</TagMark>
      <span v-if="total > 0" class="sr-only">{{ t("tab.menu_new", { n: total }) }}</span>
    </button>
    <ul v-if="open" id="tabmenu-list" class="tabmenu-list" role="menu" aria-labelledby="tabmenu-button" @keydown="menuKey">
      <li v-for="(id, index) in tabs" :key="id" role="none">
        <button :ref="(el) => (items[index] = el as HTMLElement)" type="button" role="menuitem" class="tabmenu-item" tabindex="-1" @click="pick(id)">
          {{ tabTitle(id) }}
          <TabBadge :tab="id" :count="badges[id]" />
        </button>
      </li>
    </ul>
  </div>
</template>
