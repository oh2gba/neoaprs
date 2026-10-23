<script setup lang="ts">
// The gateway's three commands as small buttons under the compose box: "List shortcuts" (`name L`: the gateway emails the list of all the shortcuts to that shortcut's address), "Remove shortcut" (`name R`) and "Get held
// mail" (`get`). The first two need a shortcut name: the To field's, when it holds one (letters and digits, no "@"), else a name field opens here. They are off while the TNC is not connected (the title says so).
// Removing asks twice ("sure?", forgotten after 5 s). The page sends them as messages to the gateway; what the gateway answers is in the thread. Beside the buttons is the gateway's count of attempts (the same field as a station's).
import { computed, ref } from "vue";
import StationAttempts from "@/components/StationAttempts.vue";
import { useSure } from "@/composables/useSure";
import type { Attempts } from "@/lib/attempts";
import { validShortcut } from "@/lib/email";
import { EMAIL_GATEWAY } from "@/lib/messages";

const props = defineProps<{ connected: boolean; to: string; attempts: Attempts }>();
const emit = defineEmits<{
  list: [name: string];
  remove: [name: string];
  get: [];
  setAttempts: [call: string, attempts: number];
  clearAttempts: [call: string];
}>();
const sure = useSure<string>(); // (the shortcut that is to be removed)

type Command = "list" | "remove";
const asking = ref<Command | null>(null);
const name = ref("");
const away = computed(() => (props.connected ? undefined : "The TNC is not connected"));
const titles: Record<Command, string> = { list: "emails the list to this shortcut's address", remove: "removes this shortcut" };
const title = (command: Command) => away.value ?? titles[command];
const ready = computed(() => props.connected && validShortcut(name.value));

function done(): void {
  name.value = "";
  asking.value = null;
}

function send(command: Command, shortcut: string): void {
  if (command === "list") {
    emit("list", shortcut.trim());
    done();
  } else {
    sure.press(shortcut.trim(), () => {
      emit("remove", shortcut.trim());
      done();
    });
  }
}

/** The button: with a shortcut name in To the command goes at once (removing after "sure?"), else the name field opens (or closes, on the same button). */
function press(command: Command): void {
  if (validShortcut(props.to)) send(command, props.to);
  else asking.value = asking.value === command ? null : command;
}

function submit(): void {
  if (asking.value !== null && ready.value) send(asking.value, name.value);
}

/** Whether the button of the command is the one waiting for its second press. */
const armed = (shortcut: string): boolean => sure.armed.value === shortcut.trim();
</script>

<template>
  <div class="mail-tools">
    <button type="button" class="btn small" :disabled="!connected" :title="title('list')" :aria-expanded="asking === 'list'" @click="press('list')">
      List shortcuts
    </button>
    <button
      type="button"
      class="btn small"
      :class="{ danger: validShortcut(to) && armed(to) }"
      :disabled="!connected"
      :title="title('remove')"
      :aria-expanded="asking === 'remove'"
      @click="press('remove')"
    >
      {{ validShortcut(to) && armed(to) ? "sure?" : "Remove shortcut" }}
    </button>
    <button type="button" class="btn small" :disabled="!connected" :title="away" @click="emit('get')">Get held mail</button>
    <form v-if="asking !== null" class="mail-shortcut" @submit.prevent="submit">
      <label class="sr-only" for="mail-shortcut">Shortcut name</label>
      <input id="mail-shortcut" v-model="name" class="input mono" type="text" placeholder="Shortcut name" autocomplete="off" spellcheck="false" />
      <button type="submit" class="btn small" :class="{ danger: asking === 'remove' }" :disabled="!ready" :title="title(asking)">
        {{ asking === "remove" ? (armed(name) ? "sure?" : "Remove") : "List" }}
      </button>
      <button type="button" class="btn small" @click="asking = null">Cancel</button>
    </form>
    <StationAttempts :call="EMAIL_GATEWAY" :attempts="attempts" @set="(c, n) => emit('setAttempts', c, n)" @clear="emit('clearAttempts', $event)" />
  </div>
</template>
