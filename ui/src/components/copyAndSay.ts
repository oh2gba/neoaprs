// Put a text on the clipboard and say so ("Copied OH2RDG"; a long text is cut in the toast).
// Used by the copy menu and the map menu. Nothing is said when the browser refuses.
import { t } from "@/i18n";
import { copyText } from "@/lib/clipboard";
import { saidText } from "@/lib/copy";

export async function copyAndSay(text: string, say: (text: string) => void): Promise<void> {
  if (await copyText(text)) say(t("copy.copied", { text: saidText(text) }));
}
