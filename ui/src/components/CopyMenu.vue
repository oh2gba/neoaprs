<script setup lang="ts">
// The small menu a right-click (the menu key, or a long press on a touch screen) opens on a call or a text anywhere but the Stations table, which has a menu of its own (StationMenu): one item for each thing under the pointer, "Copy OH2RDG", "Copy message", "Copy packet".
// The item puts the text on the clipboard and the page says so in its toast ("Copied OH2RDG"; a long message is cut short there). It opens where the pointer is and is kept inside the window, takes the focus, is moved in with the arrow keys and closed by Esc,
// a press outside it or an item that was chosen (useContextMenu). The component it belongs to opens it (useCopyMenu) and hears `close`.
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
const menu = useContextMenu({ x: () => props.x, y: () => props.y, trigger: () => props.trigger, list, buttons, close: () => emit("close") });

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
