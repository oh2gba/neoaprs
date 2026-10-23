// The state of the settings form: a draft of every value that starts as the daemon's, the keys the user changed, Save (only those, as `set_config`), and what the daemon answers: the topic
// `config` told again means it was saved, an `error` that names a key is shown under that field. A value the user has not touched follows the daemon when it changes. A form has a scope (the
// Settings tab and the Beacon tab each show their own keys): only the keys of its scope count as changed, and only those are sent.
import { computed, reactive, ref, watch, type Ref } from "vue";
import type { Command, ConfigValues } from "@/protocol/protocol";
import type { Toast } from "@/composables/useDaemon";
import { changedValues, errorKey, errorReason, groupKeys, type Scope } from "@/lib/settings";

export function useSettingsForm(
  config: Ref<ConfigValues | null>,
  lastError: Ref<Toast | null>,
  send: (command: Command) => boolean,
  scope: Scope = "settings",
) {
  const draft = reactive<Record<string, string>>({});
  const errors = reactive<Record<string, string>>({});
  const saving = ref(false);
  const saved = ref(false);

  const values = computed(() => config.value?.values ?? {});
  const defaults = computed(() => config.value?.defaults ?? {});
  const groups = computed(() => groupKeys(Object.keys(values.value), scope));
  const shown = computed(() => new Set(groups.value.flatMap((g) => g.keys)));
  const changed = computed(() => changedValues(draft, Object.fromEntries(Object.entries(values.value).filter(([key]) => shown.value.has(key)))));
  const dirty = computed(() => Object.keys(changed.value).length > 0);

  watch(
    config,
    (now, before) => {
      if (!now) return;
      for (const [key, text] of Object.entries(now.values)) {
        const untouched = !(key in draft) || draft[key] === before?.values[key] || saving.value;
        if (untouched) draft[key] = text;
      }
      if (saving.value) {
        saving.value = false;
        saved.value = true;
      }
    },
    { immediate: true },
  );

  watch(lastError, (toast) => {
    if (!toast || !saving.value) return;
    saving.value = false;
    const key = errorKey(toast.text, [...shown.value]);
    if (key) errors[key] = errorReason(toast.text, key);
  });

  function clearErrors(): void {
    for (const key of Object.keys(errors)) delete errors[key];
  }

  function save(): void {
    if (!dirty.value || saving.value) return;
    clearErrors();
    saved.value = false;
    saving.value = send({ cmd: "set_config", values: { ...changed.value } });
  }

  function edit(key: string, text: string): void {
    draft[key] = text;
    delete errors[key];
    saved.value = false;
  }

  /** Puts the daemon's own value back in the field (what the user changed is dropped). */
  function revert(): void {
    for (const key of shown.value) draft[key] = values.value[key] ?? "";
    clearErrors();
  }

  return { draft, errors, saving, saved, groups, defaults, values, changed, dirty, save, edit, revert };
}
