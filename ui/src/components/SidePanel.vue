<script setup lang="ts">
// The panel at the right of the map (on a phone the whole screen under the header, alternating with
// the map). Tabs: Messages, Stations, Nearby, Email, Bulletins, HF tests (only while an HF radio is
// on), Objects, Beacon, Packets and Settings, in one row as many as fit the measured width, the
// rest under "More". The selected tab is not bold or wider so the others do not move. The desktop
// panel has a drag handle for its width (up to 80 % of the window, leaving the map 360 px); a
// remembered width that is too large is shown clamped. Tab contents stay mounted so that filters
// and scroll positions survive. By page size (lib/layout.ts): a tablet has a CSS width and a fold
// button; a phone has neither and its tab bar starts with a Map button, so the map and the open tab
// take turns (`view`).
import TagMark from "@/components/TagMark.vue";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import TabBadge from "@/components/TabBadge.vue";
import TabMenu from "@/components/TabMenu.vue";
import type { PhoneView } from "@/composables/useLayout";
import { useRadios } from "@/composables/useRadios";
import { useTabsFit } from "@/composables/useTabsFit";
import { t } from "@/i18n";
import { PANEL_MIN, TAB_IDS, offeredTabs, tabTitle, clampWidth, panelMax, type SizeClass, type TabId } from "@/lib/layout";
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
/**
 * The right margin of the Map button (ui/src/styles/responsive.css), which the row of tabs lacks.
 */
const MAP_MARGIN = 6;
const pageWidth = ref(window.innerWidth);
const shown = computed(() => clampWidth(props.width, pageWidth.value));
const onResize = (): void => {
  pageWidth.value = window.innerWidth;
};
onMounted(() => window.addEventListener("resize", onResize));
onBeforeUnmount(() => window.removeEventListener("resize", onResize));

/**
 * The tabs of this station: HF tests only while an HF radio is on. Before the daemon has listed its
 * radios the row is drawn without it, except that a remembered HF tests tab keeps its place.
 */
const radios = useRadios();
const hfOn = computed(() => radios.enabled.value.some((radio) => radio.kind === "hf"));
const offered = computed(() => offeredTabs(hfOn.value || (!radios.told.value && props.tab === "skeds")));
/**
 * A remembered or requested tab that this station does not offer gives way to the first one
 * (HF tests is offered until the radios are listed, while it is the tab).
 */
watch(
  [offered, () => props.tab],
  ([tabs, tab]) => {
    const [first] = tabs;
    if (!tabs.includes(tab) && first !== undefined) emit("update:tab", first);
  },
  { immediate: true },
);

const phone = computed(() => props.size === "phone");
/**
 * A phone has no folded panel; a tablet's panel width comes from CSS (responsive.css), a desktop's
 * from the user.
 */
const folded = computed(() => props.collapsed && !phone.value);
/** The open tab shows; on a phone only in its turn. */
const paneOn = computed(() => !phone.value || props.view === "panel");
function pick(id: TabId): void {
  emit("update:tab", id);
  emit("update:view", "panel");
}
/**
 * The unseen messages (Messages and Email tabs), the header's count, shown on the handle while the
 * panel is folded. New bulletins and skeds are not counted.
 */
const unseen = computed(() => (props.badges.messages ?? 0) + (props.badges.email ?? 0));
const unseenTitle = computed(() => unreadText(unseen.value));

const probe = ref<HTMLElement | null>(null);
const box = ref<HTMLElement | null>(null);
const mapButton = ref<HTMLElement | null>(null);
/**
 * The tabs in the row and under More, measured on the probe (tabs drawn out of the way); the room
 * is the bar's width without a phone's Map button.
 */
const { split, measure } = useTabsFit(
  box,
  probe,
  () => (mapButton.value === null ? 0 : mapButton.value.offsetWidth + MAP_MARGIN),
  () => props.tab,
  () => props.badges,
  () => offered.value,
);
/**
 * What the More button counts, measured with the right number of digits: all offered tabs' badges
 * added.
 */
const countDigits = computed(() => "8".repeat(String(offered.value.reduce((sum, id) => sum + (props.badges[id] ?? 0), 0)).length));
/** The room of the tab names changes with a badge (more digits). */
watch(
  () => props.badges,
  () => void nextTick(measure),
  { deep: true },
);

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

/** The arrows, Home and End move to the neighbouring tab and show it; the row is one Tab stop. */
function arrow(event: KeyboardEvent, id: TabId): void {
  const list = split.value.shown;
  const at = list.indexOf(id);
  const keys: Record<string, number> = { ArrowRight: at + 1, ArrowLeft: at - 1, Home: 0, End: list.length - 1 };
  const next = keys[event.key];
  const to = next === undefined ? undefined : list[(next + list.length) % list.length];
  if (to === undefined) return;
  event.preventDefault();
  pick(to);
  void nextTick(() => document.getElementById(`tab-${to}`)?.focus());
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
    <TagMark v-if="folded && unseen > 0" class="badge fold-badge" :title="unseenTitle" aria-hidden="true">{{ unseen }}</TagMark>
    <template v-if="!folded">
      <div
        v-if="size === 'desktop'"
        class="panel-handle"
        role="separator"
        aria-orientation="vertical"
        :aria-label="t('panel.width')"
        :aria-valuemin="PANEL_MIN"
        :aria-valuemax="panelMax(pageWidth)"
        :aria-valuenow="shown"
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
          <div class="tabs" role="tablist">
            <button
              v-for="id in split.shown"
              :id="`tab-${id}`"
              :key="id"
              type="button"
              role="tab"
              class="tab"
              :class="{ active: id === tab && paneOn }"
              :aria-selected="id === tab && paneOn"
              :aria-controls="`pane-${id}`"
              :tabindex="id === tab ? 0 : -1"
              @click="pick(id)"
              @keydown="arrow($event, id)"
            >
              {{ tabTitle(id) }}
              <TabBadge :tab="id" :count="badges[id]" />
            </button>
          </div>
          <TabMenu v-if="split.hidden.length > 0" :tabs="split.hidden" :badges="badges" @pick="pick" />
          <!-- the probe: the tabs and the More button again, out of the way; their widths split -->
          <!-- the row -->
          <div ref="probe" class="tabs-probe" aria-hidden="true" inert>
            <span v-for="id in TAB_IDS" :key="id" class="tab" :data-tab="id">
              {{ tabTitle(id) }}
              <TabBadge :tab="id" :count="badges[id]" />
            </span>
            <span class="tab" data-more>{{ t("tab.more") }} <span aria-hidden="true">&#9662;</span></span>
            <span class="tab" data-more-count
              >{{ t("tab.more") }} <span aria-hidden="true">&#9662;</span> <TagMark class="badge">{{ countDigits }}</TagMark></span
            >
          </div>
        </div>
        <div v-for="id in TAB_IDS" v-show="id === tab && paneOn" :id="`pane-${id}`" :key="id" class="pane" role="tabpanel" :aria-labelledby="`tab-${id}`">
          <slot :name="id"></slot>
        </div>
      </div>
    </template>
  </aside>
</template>
