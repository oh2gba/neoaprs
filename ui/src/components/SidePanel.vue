<script setup lang="ts">
// The panel at the right of the map (under it on a narrow page): the tabs Stations, Packets, Messages, Email, Bulletins, Objects, Beacon and Settings, in one row that scrolls sideways when they do not all fit (the tab on show is not bold or wider: the others do not move) (a tab can carry a badge with a count; the folded panel shows the messages not seen, those of the Messages and the Email tab, on its handle: the same count as the header), a button that folds it away, and a handle
// to drag its width (up to 80 % of the window, the map keeping 360 px). The tab and the width are the page's to remember; a remembered width that is too much for the window is shown clamped, and is whole again when the window is wide again. The contents of every tab stay mounted, so that a filter or a scroll position is there when the tab is back.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { TAB_IDS, TAB_TITLES, clampWidth, type TabId } from "@/lib/layout";
import { badgeText, unreadText } from "@/lib/unread";

const props = defineProps<{ tab: TabId; collapsed: boolean; width: number; badges?: Partial<Record<TabId, number>> }>();
const emit = defineEmits<{ "update:tab": [tab: TabId]; "update:collapsed": [collapsed: boolean]; "update:width": [width: number] }>();

const KEY_STEP = 24;
const pageWidth = ref(window.innerWidth);
const shown = computed(() => clampWidth(props.width, pageWidth.value));
const onResize = (): void => {
  pageWidth.value = window.innerWidth;
};
onMounted(() => window.addEventListener("resize", onResize));
onBeforeUnmount(() => window.removeEventListener("resize", onResize));
/** The messages not seen (those of the Messages tab and of the Email tab), the count of the header: shown on the handle while the panel is folded, when no tab is. The new bulletins are not messages and are not in it. */
const folded = computed(() => (props.badges?.messages ?? 0) + (props.badges?.email ?? 0));
const foldedTitle = computed(() => unreadText(folded.value));

const bar = ref<HTMLElement | null>(null);
/** The tab bar is one row that scrolls sideways when the tabs do not fit; the tab that is picked (by a click, or from elsewhere on the page) is scrolled into view. */
watch(
  () => props.tab,
  () => void nextTick(() => bar.value?.querySelector(".tab.active")?.scrollIntoView?.({ block: "nearest", inline: "nearest" })),
);
/** The wheel of a mouse turns the tab bar sideways when it has more tabs than room. */
function wheel(event: WheelEvent): void {
  const el = bar.value;
  if (!el || el.scrollWidth <= el.clientWidth || event.deltaX !== 0 || event.deltaY === 0) return;
  event.preventDefault();
  el.scrollLeft += event.deltaY;
}

function drag(event: PointerEvent): void {
  const handle = event.currentTarget;
  if (!(handle instanceof HTMLElement)) return;
  handle.setPointerCapture(event.pointerId);
  const move = (e: PointerEvent): void => emit("update:width", clampWidth(window.innerWidth - e.clientX, window.innerWidth));
  const stop = (): void => {
    handle.removeEventListener("pointermove", move);
    handle.removeEventListener("pointerup", stop);
    handle.removeEventListener("pointercancel", stop);
  };
  handle.addEventListener("pointermove", move);
  handle.addEventListener("pointerup", stop);
  handle.addEventListener("pointercancel", stop);
}

function nudge(event: KeyboardEvent): void {
  const step = event.key === "ArrowLeft" ? KEY_STEP : event.key === "ArrowRight" ? -KEY_STEP : 0;
  if (step === 0) return;
  event.preventDefault();
  emit("update:width", clampWidth(shown.value + step, window.innerWidth));
}
</script>

<template>
  <aside class="panel" :class="{ collapsed }" :style="collapsed ? undefined : { '--panel-width': `${shown}px` }" aria-label="Details">
    <button
      class="panel-fold"
      type="button"
      :aria-expanded="!collapsed"
      :title="collapsed ? 'Show the panel' : 'Hide the panel'"
      @click="emit('update:collapsed', !collapsed)"
    >
      <span aria-hidden="true">{{ collapsed ? "‹" : "›" }}</span>
      <span class="sr-only">{{ collapsed ? "Show the panel" : "Hide the panel" }}{{ collapsed && folded > 0 ? `, ${foldedTitle}` : "" }}</span>
    </button>
    <span v-if="collapsed && folded > 0" class="badge fold-badge" :title="foldedTitle" aria-hidden="true">{{ folded }}</span>
    <template v-if="!collapsed">
      <div
        class="panel-handle"
        role="separator"
        aria-orientation="vertical"
        aria-label="Panel width"
        tabindex="0"
        @pointerdown.prevent="drag"
        @keydown="nudge"
      ></div>
      <div class="panel-body">
        <div ref="bar" class="tabs" role="tablist" @wheel="wheel">
          <button
            v-for="id in TAB_IDS"
            :id="`tab-${id}`"
            :key="id"
            type="button"
            role="tab"
            class="tab"
            :class="{ active: id === tab }"
            :aria-selected="id === tab"
            :aria-controls="`pane-${id}`"
            @click="emit('update:tab', id)"
          >
            {{ TAB_TITLES[id] }}
            <span v-if="badges?.[id]" class="badge" :title="badgeText(id, badges[id] ?? 0)">{{ badges[id] }}</span>
          </button>
        </div>
        <div v-for="id in TAB_IDS" v-show="id === tab" :id="`pane-${id}`" :key="id" class="pane" role="tabpanel" :aria-labelledby="`tab-${id}`">
          <slot :name="id"></slot>
        </div>
      </div>
    </template>
  </aside>
</template>
