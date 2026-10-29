// The settings form of one tab, over the settings that apply as they are changed (useSettings): the groups and keys of its scope (the Settings tab and the My station tab each show their own), and what happens when a field is
// worked: a typed field is sent when Enter is pressed or the field is left (the fields that belong together wait until the person has left all of them), a choice at once, Esc puts the value in force back, and a change that could
// cut off the device the page is open on asks first.
import { computed, ref, type Ref } from "vue";
import type { Settings } from "@/composables/useSettings";
import { confirmMessage, remotePage, TOGETHER } from "@/lib/settinglinks";
import { groupKeys, type Scope } from "@/lib/settings";
import type { ConfigValues } from "@/protocol/protocol";

/** A change that waits for a yes. */
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

  /** The field has typed text that is not yet what the daemon has. */
  const changed = (key: string): boolean => (settings.draft[key] ?? "") !== settings.expected(key);

  /** A choice (a list, a switch, a symbol, a place picked on the map) is made at once; one that could cut the page off asks first. */
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

  /** A typed field was finished with Enter (`next` is null) or left for the element `next`: it is sent, with the fields it belongs with, unless focus only moved to one of those. */
  function finish(key: string, next: EventTarget | null): void {
    const together = TOGETHER[key] ?? [key];
    const within = next instanceof Element && together.some((other) => other !== key && next.id === fieldId(other));
    if (!within) settings.commit(together);
  }

  return { groups, shown, defaults, question, changed, choose, answer, finish };
}

export type SettingsFormState = ReturnType<typeof useSettingsForm>;

/** The id of the input of a key in the form. */
export const fieldId = (key: string): string => `set-${key.replace("/", "-")}`;
