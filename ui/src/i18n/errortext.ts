// What a refusal of the daemon (an `error` message) says to the person. The daemon sends the English sentence `text` and, for most refusals, a `code` and the `params` the sentence is made of; the page says it in its own
// language from the catalogue (`error.<code>`, en/errors.ts) when it has that code, else with the daemon's English sentence (the long tail: a refusal that has no code, or a code only the daemon knows). The page goes by
// `cmd`, `key` and `code`, never by the words of `text`; the only thing it does with the sentence is to take the command and the setting off its front.
import { hasMessage, t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import type { Params } from "@/i18n/message";
import { CONFIG_KEYS, LIMITS, TNC_PROFILES } from "@/protocol/lists";
import type { ErrorMessage } from "@/protocol/protocol";

export type Failure = Pick<ErrorMessage, "text" | "cmd" | "key"> & Partial<Pick<ErrorMessage, "code" | "params">>;

/** What some sentences list and the daemon does not send in `params`, from the lists the daemon has given the page. */
const LISTS: Params = {
  profiles: TNC_PROFILES.map((p) => p.key).join(", "),
  settings: CONFIG_KEYS.join(", "),
  forbidden: [...LIMITS.message.forbidden].join(" "),
  name_forbidden: [...LIMITS.object.nameForbidden].join(" "),
};

/** The id of the sentence the catalogue has for this refusal, or null. */
function idOf(error: Failure): MessageId | null {
  const id = `error.${error.code ?? "other"}`;
  return error.code !== "other" && hasMessage(id) ? id : null;
}

/** The prefix the daemon puts before a reason: the command, then the setting. */
function prefix(error: Failure): string {
  return (error.cmd === "" ? "" : `${error.cmd}: `) + (error.key === null ? "" : `${error.key}: `);
}

/** What is wrong, without the command and the setting in front: from the catalogue for a code it has, else the daemon's English words with those taken off the front. */
export function errorReason(error: Failure): string {
  const id = idOf(error);
  if (id) return t(id, { ...LISTS, ...error.params });
  let text = error.text;
  if (error.cmd !== "" && text.startsWith(`${error.cmd}: `)) text = text.slice(error.cmd.length + 2);
  if (error.key !== null && text.startsWith(`${error.key}: `)) text = text.slice(error.key.length + 2);
  return text;
}

/** The whole line for a toast, the way the daemon writes it: the command, the setting, the reason. */
export function errorLine(error: Failure): string {
  return idOf(error) ? prefix(error) + errorReason(error) : error.text;
}
