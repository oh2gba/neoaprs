// The New key button of the access key: it asks twice ("sure?", for a new key logs every other device out), then asks the daemon for one. The daemon tells the page the new key in the topic `config`; only a failure is shown.
import { computed, ref } from "vue";
import { useSure } from "@/composables/useSure";
import { renewKey } from "@/lib/access";

export const KEY_KEY = "web/key";

export function useNewKey(renew: () => Promise<string> = renewKey) {
  const running = ref(false);
  const result = ref<{ ok: boolean; text: string } | null>(null);
  const sure = useSure<string>();

  async function make(): Promise<void> {
    running.value = true;
    result.value = null;
    const problem = await renew();
    running.value = false;
    if (problem) result.value = { ok: false, text: problem };
  }

  return { running, result, armed: computed(() => sure.armed.value === KEY_KEY), press: () => sure.press(KEY_KEY, () => void make()) };
}
