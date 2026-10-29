// What the station panel and the menu of a row of the Stations table do that is not the page's navigation: a directed query is sent to the daemon (`query`; if the daemon refuses, its error is the toast that replaces "Asked
// OH2XYZ for its status"), the operator's own query too (`custom`, with its text, upper-cased: lib/query.ts), and the call is put on the clipboard.
import { copyAndSay } from "@/components/copyAndSay";
import { t } from "@/i18n";
import type { QueryKind } from "@/lib/stations";
import type { Command } from "@/protocol/protocol";

export function useStationActions(send: (command: Command) => boolean, say: (text: string) => void) {
  /** Asks the station the query, or the operator's own (`custom` with its `text`); the page says so when the command was sent. */
  function ask(call: string, kind: QueryKind | "custom", text?: string): void {
    if (kind === "custom") {
      if (text !== undefined && send({ cmd: "query", call, kind, text })) say(t("station.ask.custom", { call, text }));
    } else if (send({ cmd: "query", call, kind })) say(t(`station.ask.${kind}`, { call }));
  }

  /** Copies the call; the page says so when it is on the clipboard. */
  async function copy(call: string): Promise<void> {
    await copyAndSay(call, say);
  }

  return { ask, copy };
}
