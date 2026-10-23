// The settings as they apply while they are changed (no Save button): a draft of every value that starts as the daemon's, and a change that is made (a choice at once, a typed field on Enter or when it is left) goes to the daemon
// as a `set_config` of just the keys that differ, after the page's own check of the text. One save is out at a time (useSettingsQueue); what the person sees of it is useSettingsFeedback. The daemon's reason for a refusal is
// shown under the key it names. A value the person has not touched follows the daemon when it changes (another device, the radio found); a field being edited, or one the daemon refused, keeps what was typed.
// One of these is shared by the Settings tab and the Beacon tab, so that there is one queue; the keys each tab shows are `useSettingsForm`.
import { computed, getCurrentScope, onScopeDispose, reactive, type Ref } from "vue";
import type { Toast } from "@/composables/useDaemon";
import { useSettingsAnswers } from "@/composables/useSettingsAnswers";
import { useSettingsFeedback } from "@/composables/useSettingsFeedback";
import { useSettingsQueue, type Request } from "@/composables/useSettingsQueue";
import { pairProblems, problemOf, sameValue } from "@/lib/settingcheck";
import { changeName, linkedValues } from "@/lib/settinglinks";
import type { Command, ConfigValues } from "@/protocol/protocol";

export function useSettings(config: Ref<ConfigValues | null>, lastError: Ref<Toast | null>, send: (command: Command) => boolean) {
  const draft = reactive<Record<string, string>>({});
  const errors = reactive<Record<string, string>>({});
  const feedback = useSettingsFeedback();
  const values = computed(() => config.value?.values ?? {});

  /** The request was not saved: the reason under the key, and a refused choice shows the value in force again. */
  function refuse(request: Request, reason: string, key = request.keys[0] ?? ""): void {
    errors[key] = reason;
    for (const k of request.revert) if (!queue.waiting(k)) draft[k] = values.value[k] ?? "";
  }
  const queue = useSettingsQueue(send, () => values.value, refuse);
  if (getCurrentScope()) onScopeDispose(queue.dispose);

  /** The key is being edited: the draft is the typing, nothing is sent. */
  function edit(key: string, text: string): void {
    draft[key] = text;
    delete errors[key];
  }

  /** Esc: the value the key has (or will have) comes back. */
  function cancel(key: string): void {
    draft[key] = queue.expected(key);
    delete errors[key];
  }

  function enqueue(request: Request): void {
    feedback.dismissUndo(); // (earlier changes are just applied: the toast covers the latest)
    queue.enqueue(request);
  }

  /** Checks the keys as typed and sends those that differ from what they have, together in one request (`revert`: a refused choice shows the old value again). Nothing is sent when the page finds a problem with any of them. */
  function commit(keys: readonly string[], revert = false): void {
    for (const key of keys) delete errors[key];
    const problems = keys.map((key) => [key, problemOf(key, draft[key] ?? "")] as const).filter(([, problem]) => problem !== "");
    for (const [key, problem] of problems) errors[key] = problem;
    const incomplete = problems.length > 0 ? {} : pairProblems(keys, draft);
    Object.assign(errors, incomplete);
    if (problems.length > 0 || Object.keys(incomplete).length > 0) return;
    const sent: Record<string, string> = {};
    for (const key of keys) {
      const text = draft[key] ?? "";
      if (sameValue(key, text, queue.expected(key))) draft[key] = queue.expected(key);
      else sent[key] = text;
    }
    for (const [key, text] of Object.entries({ ...sent })) Object.assign(sent, linkedValues(key, text, draft));
    const names = Object.keys(sent);
    for (const key of names) draft[key] = sent[key] ?? "";
    if (names.length > 0) enqueue({ values: sent, keys: names, label: changeName(names), revert: revert ? names : [], previous: {}, undo: false });
  }

  /** A choice made at once: the keys take these texts and are sent. */
  function change(choices: Readonly<Record<string, string>>): void {
    for (const [key, text] of Object.entries(choices)) edit(key, text);
    commit(Object.keys(choices), true);
  }

  /** Puts back what the latest change replaced, in one request. */
  function undoLast(): void {
    const last = feedback.undo.value;
    if (!last) return;
    const keys = Object.keys(last.values);
    for (const key of keys) edit(key, last.values[key] ?? "");
    enqueue({ values: { ...last.values }, keys, label: last.label, revert: [], previous: {}, undo: true });
  }

  useSettingsAnswers(config, lastError, draft, queue, feedback, (request, reason, key) => refuse(request, reason, key));

  return {
    draft,
    errors,
    values,
    undo: feedback.undo,
    announcement: feedback.announcement,
    saving: queue.saving,
    expected: queue.expected,
    edit,
    cancel,
    commit,
    change,
    undoLast,
    dismissUndo: feedback.dismissUndo,
  };
}

export type Settings = ReturnType<typeof useSettings>;
