// What the person is given of a change that applies as it is made (composables/useSettings.ts): a line for a screen reader ("Saved"). Nothing is shown beside the field and no toast comes up: nothing on the page may change size or move when a setting applies,
// and a refusal is shown under its field (useSettingsAnswers).
import { ref } from "vue";
import { t } from "@/i18n";

export function useSettingsFeedback() {
  const announcement = ref({ text: "", n: 0 });

  const say = (text: string): void => void (announcement.value = { text, n: announcement.value.n + 1 });

  /** The request was saved: a screen reader is told. */
  const saved = (): void => say(t("settings.saved"));

  return { announcement, say, saved };
}
