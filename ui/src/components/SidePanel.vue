<script setup lang="ts">
// The panel at the right of the map (on a phone it is the whole screen under the header, in turns with the map): the tabs Messages, Stations, Nearby, Email, Bulletins, Objects, Beacon, Packets and Settings, in one row (the tab on show is not bold or wider: the others do not move) when they fit in the width of the panel, measured, and when they do not as one button "☰ Messages" with a menu of them all (TabMenu) (a tab can carry a badge with a count; the folded panel shows the messages not seen, those of the Messages and the Email tab, on its handle: the same count as the header), a button that folds it away, under the open tab a footer (the slot `footer`: the version and what is wrong with the radio; not on a phone's map turn, nor on a folded panel), and a handle
// to drag its width (up to 80 % of the window, the map keeping 360 px). The tab and the width are the page's to remember; a remembered width that is too much for the window is shown clamped, and is whole again when the window is wide again. The contents of every tab stay mounted, so that a filter or a scroll position is there when the tab is back.
// By the size of the page (lib/layout.ts): a desktop has the handle and the user's width; a tablet has a width of its own (CSS) and the fold button; a phone has neither, and its tab bar starts with a Map button: the map and the open tab take turns (`view`),
// a tab picked in the bar brings the panel, the Map button the map, and the contents of the tab are the whole area under the bar.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import TabBadge from "@/components/TabBadge.vue";
import TabMenu from "@/components/TabMenu.vue";
import type { PhoneView } from "@/composables/useLayout";
import { useTabsFit } from "@/composables/useTabsFit";
import { t } from "@/i18n";
import { TAB_IDS, tabTitle, clampWidth, type SizeClass, type TabId } from "@/lib/layout";
import { unreadText } from "@/lib/unread";

const props = withDefaults(
  defineProps<{ tab: TabId; collapsed: boolean; width: number; badges?: Partial<Record<TabId, number>>; size?: SizeClass; view?: PhoneView }>(),
  { badges: () => ({}), size: "desktop", view: "panel" },
);
const emit = defineEmits<{
  "update:tab": [tab: TabId];
  "update:collapsed": [collapsed: boolean];
  "update:width": [width: number];
  "update:view": [view: PhoneView];
}>();

const KEY_STEP = 24;
/** The left margin of the Map button (ui/src/styles/responsive.css), which the row of tabs does not have. */
const MAP_MARGIN = 6;
const pageWidth = ref(window.innerWidth);
const shown = computed(() => clampWidth(props.width, pageWidth.value));
const onResize = (): void => {
  pageWidth.value = window.innerWidth;
};
onMounted(() => window.addEventListener("resize", onResize));
onBeforeUnmount(() => window.removeEventListener("resize", onResize));

const phone = computed(() => props.size === "phone");
/** A phone has no folded panel (the map has its turn); a tablet's panel has the width of its size (ui/src/styles/responsive.css), a desktop's the user's. */
const folded = computed(() => props.collapsed && !phone.value);
/** The open tab shows; on a phone only in its turn. */
const paneOn = computed(() => !phone.value || props.view === "panel");
function pick(id: TabId): void {
  emit("update:tab", id);
  emit("update:view", "panel");
}
/** The messages not seen (those of the Messages tab and of the Email tab), the count of the header: shown on the handle while the panel is folded, when no tab is. The new bulletins are not messages and are not in it. */
const unseen = computed(() => (props.badges.messages ?? 0) + (props.badges.email ?? 0));
const unseenTitle = computed(() => unreadText(unseen.value));

const bar = ref<HTMLElement | null>(null);
const box = ref<HTMLElement | null>(null);
const mapButton = ref<HTMLElement | null>(null);
/** The tabs in a row when they fit in the width the bar has (the Map button of a phone first), else one button with a menu of them (TabMenu): measured, so a wide phone and a narrow panel on a wide screen both get the right one. */
const { fits, measure } = useTabsFit(box, bar, () => (mapButton.value === null ? 0 : mapButton.value.offsetWidth + MAP_MARGIN));
/** The room of the tab names changes with a badge (more digits). */
watch(
  () => props.badges,
  () => void nextTick(measure),
  { deep: true },
);
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
  <aside
    class="panel"
    :class="{ collapsed: folded, 'bar-only': !paneOn }"
    :style="folded || size !== 'desktop' ? undefined : { '--panel-width': `${shown}px` }"
    :aria-label="t('panel.label')"
  >
    <button
      v-if="!phone"
      class="panel-fold"
      type="button"
      :aria-expanded="!folded"
      :title="folded ? t('panel.show') : t('panel.hide')"
      @click="emit('update:collapsed', !folded)"
    >
      <span aria-hidden="true">{{ folded ? "‹" : "›" }}</span>
      <span class="sr-only">{{ folded ? (unseen > 0 ? t("panel.show_unseen", { unseen: unseenTitle }) : t("panel.show")) : t("panel.hide") }}</span>
    </button>
    <span v-if="folded && unseen > 0" class="badge fold-badge" :title="unseenTitle" aria-hidden="true">{{ unseen }}</span>
    <template v-if="!folded">
      <div
        v-if="size === 'desktop'"
        class="panel-handle"
        role="separator"
        aria-orientation="vertical"
        :aria-label="t('panel.width')"
        tabindex="0"
        @pointerdown.prevent="drag"
        @keydown="nudge"
      ></div>
      <div class="panel-body">
        <div ref="box" class="tabbar">
          <button
            v-if="phone"
            ref="mapButton"
            type="button"
            class="tab tab-map"
            :class="{ active: !paneOn }"
            :aria-pressed="!paneOn"
            @click="emit('update:view', 'map')"
          >
            {{ t("panel.map") }}
          </button>
          <TabMenu v-if="!fits" :tab="tab" :badges="badges" :on="paneOn" @pick="pick" />
          <div ref="bar" class="tabs" :class="{ measuring: !fits }" role="tablist" :aria-hidden="fits ? undefined : 'true'" @wheel="wheel">
            <button
              v-for="id in TAB_IDS"
              :id="`tab-${id}`"
              :key="id"
              type="button"
              role="tab"
              class="tab"
              :class="{ active: id === tab && paneOn }"
              :aria-selected="id === tab && paneOn"
              :aria-controls="`pane-${id}`"
              @click="pick(id)"
            >
              {{ tabTitle(id) }}
              <TabBadge :tab="id" :count="badges[id]" />
            </button>
          </div>
        </div>
        <div v-for="id in TAB_IDS" v-show="id === tab && paneOn" :id="`pane-${id}`" :key="id" class="pane" role="tabpanel" :aria-labelledby="`tab-${id}`">
          <slot :name="id"></slot>
        </div>
        <slot v-if="paneOn" name="footer"></slot>
      </div>
    </template>
  </aside>
</template>
