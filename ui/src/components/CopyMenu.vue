<script setup lang="ts">
// The small menu opened by right-click, the menu key or a long press on a call or text anywhere
// but the Stations table (StationMenu): one item per thing under the pointer, such as "Copy
// OH2RDG" or "Copy message". It behaves as every menu of the page (useContextMenu); the owner
// opens it (useCopyMenu) and handles `close`.
import { ref } from "vue";
import { useContextMenu } from "@/composables/useContextMenu";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { t } from "@/i18n";
import { copyAndSay } from "@/components/copyAndSay";
import type { CopyItem } from "@/lib/copy";

const props = defineProps<{ items: readonly CopyItem[]; x: number; y: number; trigger: HTMLElement | null }>();
const emit = defineEmits<{ close: [] }>();
const { say } = useDaemonContext();

const list = ref<HTMLElement | null>(null);
const buttons = ref<HTMLElement[]>([]);
const menu = useContextMenu({
  x: () => props.x,
  y: () => props.y,
  trigger: () => props.trigger,
  list,
  buttons,
  close: () => emit("close"),
});

function label(item: CopyItem): string {
  switch (item.kind) {
    case "call":
      return t("copy.call", { call: item.text });
    case "message":
      return t("copy.message");
    case "packet":
      return t("copy.packet");
    case "address":
      return t("copy.address");
    case "name":
      return t("copy.name");
  }
}

async function choose(item: CopyItem): Promise<void> {
  menu.done();
  await copyAndSay(item.text, say);
}
</script>

<template>
  <ul
    ref="list"
    class="ctxmenu copymenu"
    role="menu"
    :aria-label="t('copy.menu_label')"
    :style="{ left: `${menu.at.value.left}px`, top: `${menu.at.value.top}px` }"
    @keydown="menu.onKey"
    @contextmenu.prevent
  >
    <li v-for="(item, index) in items" :key="`${item.kind}:${item.text}`" role="none">
      <button
        :ref="(el) => (buttons[index] = el as HTMLElement)"
        type="button"
        role="menuitem"
        class="ctxmenu-item"
        tabindex="-1"
        :data-item="item.kind"
        @click="choose(item)"
      >
        {{ label(item) }}
      </button>
    </li>
  </ul>
</template>
