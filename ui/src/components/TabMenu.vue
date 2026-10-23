<script setup lang="ts">
// The tabs of the panel as one button, for a panel too narrow for the row of tabs (SidePanel measures that): "☰ Messages", the name of the open tab, with the count of everything that has a badge (the messages and the mail not seen, the new bulletins) when there is any.
// It opens a menu with all the tabs in their order, each with its badge, the open one marked (aria-current); a click on one picks it and closes the menu, Esc and a click outside close it, Up and Down, Home and End move in it (Down or Up on the button opens it on the open tab or the last).
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { TAB_IDS, TAB_TITLES, type TabId } from "@/lib/layout";
import { badgeText } from "@/lib/unread";

const props = defineProps<{ tab: TabId; badges: Partial<Record<TabId, number>>; on: boolean }>();
const emit = defineEmits<{ pick: [tab: TabId] }>();

const open = ref(false);
const root = ref<HTMLElement | null>(null);
const button = ref<HTMLElement | null>(null);
const items = ref<HTMLElement[]>([]);
const total = computed(() => TAB_IDS.reduce((sum, id) => sum + (props.badges[id] ?? 0), 0));

function focusItem(index: number): void {
  items.value[(index + TAB_IDS.length) % TAB_IDS.length]?.focus();
}
async function show(index = TAB_IDS.indexOf(props.tab)): Promise<void> {
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
  void show(event.key === "ArrowDown" ? TAB_IDS.indexOf(props.tab) : TAB_IDS.length - 1);
}
function menuKey(event: KeyboardEvent): void {
  const at = items.value.findIndex((item) => item === document.activeElement);
  const step: Record<string, () => void> = {
    ArrowDown: () => focusItem(at + 1),
    ArrowUp: () => focusItem(at - 1),
    Home: () => focusItem(0),
    End: () => focusItem(TAB_IDS.length - 1),
  };
  if (event.key === "Escape") {
    event.preventDefault();
    event.stopPropagation();
    close(true);
  } else if (event.key === "Tab") {
    close(false);
  } else if (step[event.key]) {
    event.preventDefault();
    step[event.key]?.();
  }
}
function outside(event: Event): void {
  if (open.value && event.target instanceof Node && !root.value?.contains(event.target)) close(false);
}
onMounted(() => document.addEventListener("pointerdown", outside));
onBeforeUnmount(() => document.removeEventListener("pointerdown", outside));
</script>

<template>
  <div ref="root" class="tabmenu">
    <button
      id="tabmenu-button"
      ref="button"
      type="button"
      class="tab tabmenu-button"
      :class="{ active: on }"
      aria-haspopup="menu"
      :aria-expanded="open"
      aria-controls="tabmenu-list"
      @click="toggle"
      @keydown="buttonKey"
    >
      <span aria-hidden="true">&#9776;</span> {{ TAB_TITLES[tab] }}
      <span v-if="total > 0" class="badge" aria-hidden="true">{{ total }}</span>
      <span v-if="total > 0" class="sr-only">, {{ total }} new</span>
    </button>
    <ul v-if="open" id="tabmenu-list" class="tabmenu-list" role="menu" aria-labelledby="tabmenu-button" @keydown="menuKey">
      <li v-for="(id, index) in TAB_IDS" :key="id" role="none">
        <button
          :ref="(el) => (items[index] = el as HTMLElement)"
          type="button"
          role="menuitem"
          class="tabmenu-item"
          tabindex="-1"
          :aria-current="id === tab ? 'page' : undefined"
          @click="pick(id)"
        >
          {{ TAB_TITLES[id] }}
          <span v-if="badges[id]" class="badge" :title="badgeText(id, badges[id] ?? 0)">{{ badges[id] }}</span>
        </button>
      </li>
    </ul>
  </div>
</template>
