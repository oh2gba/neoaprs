// A text put on the clipboard and the page saying so ("Copied OH2RDG"; a long text is cut short in the toast): what the copy menu and the map's menu do when an item is chosen. Nothing is said when the browser refused.
import { t } from "@/i18n";
import { copyText } from "@/lib/clipboard";
import { saidText } from "@/lib/copy";

export async function copyAndSay(text: string, say: (text: string) => void): Promise<void> {
  if (await copyText(text)) say(t("copy.copied", { text: saidText(text) }));
}
