// The settings form of one tab, over the settings that apply as changed (useSettings): the
// groups and keys of its scope, and what a field does. A typed field is sent on Enter or when
// left (fields that belong together wait until all are left), a choice at once, Esc puts the value
// in force back, and a change that could cut off the device the page is open on asks first.
import { computed, ref, type Ref } from "vue";
import type { Settings } from "@/composables/useSettings";
import { confirmMessage, remotePage, togetherOf } from "@/lib/settinglinks";
import { inputId } from "@/lib/settingsradio";
import { groupKeys, type Scope } from "@/lib/settings";
import type { ConfigValues } from "@/protocol/protocol";

export interface Question {
  key: string;
  text: string;
  message: string;
}

export function useSettingsForm(config: Ref<ConfigValues | null>, settings: Settings, scope: Scope = "settings", remote: () => boolean = remotePage) {
  const defaults = computed(() => config.value?.defaults ?? {});
  const groups = computed(() => groupKeys(Object.keys(settings.values.value), scope));
  const shown = computed(() => new Set(groups.value.flatMap((g) => g.keys)));
  const question = ref<Question | null>(null);

  const changed = (key: string): boolean => (settings.draft[key] ?? "") !== settings.expected(key);

  /** A choice is made at once; one that could cut the page off asks first. */
  function choose(choices: Record<string, string>): void {
    const [key, text] = Object.entries(choices)[0] ?? ["", ""];
    const message = Object.keys(choices).length === 1 ? confirmMessage(key, text, remote()) : null;
    if (message === null) return settings.change(choices);
    settings.edit(key, text);
    question.value = { key, text, message };
  }

  function answer(yes: boolean): void {
    const asked = question.value;
    question.value = null;
    if (!asked) return;
    if (yes) settings.change({ [asked.key]: asked.text });
    else settings.cancel(asked.key);
  }

  /**
   * A typed field was finished with Enter (`next` null) or left for `next`: send it with its group
   * unless focus moved within the group.
   */
  function finish(key: string, next: EventTarget | null): void {
    const together = togetherOf(key);
    const within = next instanceof Element && together.some((other) => other !== key && next.id === fieldId(other));
    if (!within) settings.commit(together);
  }

  return { groups, shown, defaults, question, changed, choose, answer, finish };
}

export type SettingsFormState = ReturnType<typeof useSettingsForm>;

/** The id of the input of a key (lib/settingsradio.ts `inputId`: every "/" a "-"). */
export const fieldId = inputId;
