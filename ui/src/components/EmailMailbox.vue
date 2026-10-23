<script setup lang="ts">
// The "Mailbox" button of the Email tab and the menu it opens: "Fetch held mail" (`get`: the gateway sends again the mail it holds for this station; off while the TNC is not connected or a `get` is still being sent, the title says why) and "Shortcuts…" (the tab opens
// the form for them). The menu closes with a choice, Esc, or a click or tap outside it.
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { GET_HELD } from "@/lib/email";

const props = withDefaults(defineProps<{ connected: boolean; fetching?: boolean }>(), { fetching: false });
const emit = defineEmits<{ get: []; shortcuts: [] }>();

const open = ref(false);
const root = ref<HTMLElement | null>(null);
const away = computed(() => (!props.connected ? "The TNC is not connected" : props.fetching ? "Already fetching held mail" : undefined));

function outside(event: Event): void {
  if (!(event.target instanceof Node) || !root.value?.contains(event.target)) open.value = false;
}

function choose(act: "get" | "shortcuts"): void {
  open.value = false;
  if (act === "get") emit("get");
  else emit("shortcuts");
}

watch(open, (now) => {
  const act = now ? document.addEventListener.bind(document) : document.removeEventListener.bind(document);
  act("pointerdown", outside);
  act("focusin", outside);
});
onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", outside);
  document.removeEventListener("focusin", outside);
});
</script>

<template>
  <div ref="root" class="mail-menu" @keydown.esc="open = false">
    <button type="button" class="btn" aria-haspopup="menu" :aria-expanded="open" @click="open = !open">
      Mailbox
      <svg
        width="10"
        height="10"
        viewBox="0 0 10 10"
        fill="none"
        stroke="currentColor"
        stroke-width="1.6"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <path d="M2 3.5l3 3 3-3" />
      </svg>
    </button>
    <ul v-if="open" class="menu-list" role="menu" aria-label="Mailbox">
      <li role="none">
        <button
          type="button"
          class="menu-item"
          role="menuitem"
          :disabled="away !== undefined"
          :title="away ?? `Sends '${GET_HELD}': the gateway sends again the mail it holds for you`"
          @click="choose('get')"
        >
          Fetch held mail
        </button>
      </li>
      <li role="none">
        <button type="button" class="menu-item" role="menuitem" @click="choose('shortcuts')">Shortcuts…</button>
      </li>
    </ul>
  </div>
</template>
