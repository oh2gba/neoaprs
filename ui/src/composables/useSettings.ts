// The settings as they apply while changed (no Save button): a draft of every value, starting as
// the daemon's. A change (a choice at once, a typed field on Enter or blur) goes as a
// `set_config` of the changed keys after the page's own check. One save is out at a time
// (useSettingsQueue); the person's view of it is useSettingsFeedback. A refusal shows under the
// key it names. An untouched value follows the daemon; a field being edited or refused keeps what
// was typed. The Settings and My station tabs share one instance, so there is one queue; each
// tab's keys are `useSettingsForm`. Radio settings (`radio/3/port`, `email/radio`) from
// `config.radio_values` are saved, held and refused like the rest.
import { computed, getCurrentScope, onScopeDispose, reactive, type Ref } from "vue";
import type { Toast } from "@/composables/useDaemon";
import type { RadioNames } from "@/i18n/errortext";
import { useSettingsAnswers } from "@/composables/useSettingsAnswers";
import { useSettingsFeedback } from "@/composables/useSettingsFeedback";
import { useSettingsQueue, type Request } from "@/composables/useSettingsQueue";
import { pairProblems, problemOf, sameValue } from "@/lib/fieldcheck";
import { linkedValues } from "@/lib/settinglinks";
import type { Command, ConfigValues } from "@/protocol/protocol";

export function useSettings(
  config: Ref<ConfigValues | null>,
  lastError: Ref<Toast | null>,
  send: (command: Command) => boolean,
  radios?: RadioNames,
) {
  const draft = reactive<Record<string, string>>({});
  const errors = reactive<Record<string, string>>({});
  const feedback = useSettingsFeedback();
  const whole = computed<ConfigValues | null>(() => (config.value === null ? null : withRadios(config.value)));
  const values = computed(() => whole.value?.values ?? {});

  function refuse(request: Request, reason: string, key = request.keys[0] ?? ""): void {
    errors[key] = reason;
    for (const k of request.revert) if (!queue.waiting(k)) draft[k] = values.value[k] ?? "";
  }
  const queue = useSettingsQueue(send, () => values.value, refuse);
  if (getCurrentScope()) onScopeDispose(queue.dispose);

  function edit(key: string, text: string): void {
    draft[key] = text;
    delete errors[key];
  }

  function cancel(key: string): void {
    draft[key] = queue.expected(key);
    delete errors[key];
  }

  /**
   * The keys whose draft differs from the value they have or will have; others are put back as
   * written.
   */
  function differing(keys: readonly string[]): Record<string, string> {
    const sent: Record<string, string> = {};
    for (const key of keys) {
      const text = draft[key] ?? "";
      if (sameValue(key, text, queue.expected(key))) draft[key] = queue.expected(key);
      else sent[key] = text;
    }
    return sent;
  }

  /**
   * Check the typed keys and send those that differ in one request; `revert` shows the old value of
   * a refused choice. Nothing is sent if any key has a problem.
   */
  function commit(keys: readonly string[], revert = false, first = false): void {
    for (const key of keys) delete errors[key];
    const problems = keys
      .map((key) => [key, problemOf(key, draft[key] ?? "")] as const)
      .filter(([, problem]) => problem !== "");
    for (const [key, problem] of problems) errors[key] = problem;
    const incomplete = problems.length > 0 ? {} : pairProblems(keys, draft);
    Object.assign(errors, incomplete);
    if (problems.length > 0 || Object.keys(incomplete).length > 0) return;
    const sent = differing(keys);
    for (const [key, text] of Object.entries({ ...sent })) Object.assign(sent, linkedValues(key, text, draft));
    const names = Object.keys(sent);
    for (const key of names) draft[key] = sent[key] ?? "";
    if (names.length > 0) queue.enqueue({ values: sent, keys: names, revert: revert ? names : [] }, first);
  }

  /** `first`: sent before every other waiting save (useSettingsQueue). */
  function change(choices: Readonly<Record<string, string>>, first = false): void {
    for (const [key, text] of Object.entries(choices)) edit(key, text);
    commit(Object.keys(choices), true, first);
  }

  useSettingsAnswers(
    whole,
    lastError,
    draft,
    queue,
    feedback,
    (request, reason, key) => refuse(request, reason, key),
    radios,
  );

  return {
    draft,
    errors,
    values,
    defaults: computed(() => whole.value?.defaults ?? {}),
    announcement: feedback.announcement,
    saving: queue.saving,
    expected: queue.expected,
    edit,
    cancel,
    commit,
    change,
  };
}

export type Settings = ReturnType<typeof useSettings>;

/** The settings with the radios' own beside them (`radio_values`, `radio_defaults`). */
function withRadios(config: ConfigValues): ConfigValues {
  const radioValues = config.radio_values ?? {};
  const radioDefaults = config.radio_defaults ?? {};
  if (Object.keys(radioValues).length === 0 && Object.keys(radioDefaults).length === 0) return config;
  return {
    ...config,
    values: { ...config.values, ...radioValues },
    defaults: { ...config.defaults, ...radioDefaults },
  };
}
