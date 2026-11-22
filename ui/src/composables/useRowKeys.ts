// Up and Down on a row of the Stations table select the previous or next station as a click does
// (with Ctrl or Cmd adding its card); Home and End go to the first and last. `calls` gives the
// rows in order and `stationRowId` names the row element that takes the focus. Only a key on the
// row itself counts, not one on a button in it. `select` is what a click does.
import { stationRowId } from "@/lib/stations";

const JUMP: Record<string, number> = { ArrowDown: 1, ArrowUp: -1, Home: -Infinity, End: Infinity };

interface RowKeys {
  calls: () => readonly string[];
  select: (call: string, multi: boolean) => void;
}

export function useRowKeys({ calls, select }: RowKeys): (event: KeyboardEvent, call: string) => void {
  return (event, call) => {
    const step = JUMP[event.key];
    if (step === undefined || event.target !== event.currentTarget) return;
    const list = calls();
    const next = list[Math.max(0, Math.min(list.length - 1, list.indexOf(call) + step))];
    if (next === undefined) return;
    event.preventDefault();
    document.getElementById(stationRowId(next))?.focus();
    select(next, event.ctrlKey || event.metaKey);
  };
}
