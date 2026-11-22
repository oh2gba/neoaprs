// What the station panel and a Stations table row's menu do beyond navigation: send a directed
// query (`query`; a refusal is the toast that replaces "Asked OH2XYZ for its status"), the
// operator's own query (`custom`, text upper-cased: lib/query.ts), and copy the call.
import { copyAndSay } from "@/components/copyAndSay";
import { t } from "@/i18n";
import type { QueryKind } from "@/lib/stations";
import type { Command } from "@/protocol/protocol";

export function useStationActions(send: (command: Command) => boolean, say: (text: string) => void) {
  function ask(call: string, kind: QueryKind | "custom", text?: string): void {
    if (kind === "custom") {
      if (text !== undefined && send({ cmd: "query", call, kind, text })) say(t("station.ask.custom", { call, text }));
    } else if (send({ cmd: "query", call, kind })) say(t(`station.ask.${kind}`, { call }));
  }

  async function copy(call: string): Promise<void> {
    await copyAndSay(call, say);
  }

  return { ask, copy };
}
