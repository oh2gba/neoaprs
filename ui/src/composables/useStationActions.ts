// What the menu of a row of the Stations table does that is not the page's navigation: a directed query is sent to the daemon (`query`; if the daemon refuses, its error is the toast that replaces "Asked OH2XYZ for its status"), and the call is put on the clipboard.
import { t } from "@/i18n";
import { copyText } from "@/lib/clipboard";
import type { QueryKind } from "@/lib/stations";
import type { Command } from "@/protocol/protocol";

export function useStationActions(send: (command: Command) => boolean, say: (text: string) => void) {
  /** Asks the station the query; the page says so when the command was sent. */
  function ask(call: string, kind: QueryKind): void {
    if (send({ cmd: "query", call, kind })) say(t(`station.ask.${kind}`, { call }));
  }

  /** Copies the call; the page says so when it is on the clipboard. */
  async function copy(call: string): Promise<void> {
    if (await copyText(call)) say(t("station.menu.copied", { call }));
  }

  return { ask, copy };
}
