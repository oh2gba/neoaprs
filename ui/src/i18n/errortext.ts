// What a refusal of the daemon (an `error` message) says to the person. The daemon sends the English sentence `text` and, for most refusals, a `code` and the `params` the sentence is made of; the page says it in its own
// language from the catalogue (`error.<code>`, en/errors.ts) when it has that code, else with the daemon's English sentence (the long tail: a refusal that has no code, or a code only the daemon knows). The page goes by
// `cmd`, `key` and `code`, never by the words of `text`; the only thing it does with the sentence is to take the command and the setting off its front. A refusal that names a radio by the daemon's English name (`name`, the
// holder of a device) carries that radio's id too (`radio`, `held_by`): given the page's radios (`useRadios()`), the sentence says the radio as the page calls it (lib/radios.ts `radioLabel`), in the page's language.
import { hasMessage, t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import type { Params } from "@/i18n/message";
import type { PageRadio, RadioId } from "@/lib/radios";
import { CONFIG_KEYS, LIMITS, TNC_PROFILES } from "@/protocol/lists";
import type { ErrorMessage } from "@/protocol/protocol";

export type Failure = Pick<ErrorMessage, "text" | "cmd" | "key"> & Partial<Pick<ErrorMessage, "code" | "params">>;

/** Where the page finds a radio by its id: `useRadios()`, which has removed radios too. */
export interface RadioNames {
  byId: (id: RadioId) => Pick<PageRadio, "name" | "kind"> | undefined;
}

/** The word of each kind, as lib/radios.ts names a radio by it (its `KIND_WORDS`, which this file cannot import: lib/radios.ts imports this one). errortext.test.ts holds the two together. */
const KIND_WORDS: Record<PageRadio["kind"], MessageId> = { fm: "channel.fm", hf: "channel.hf", lora: "channel.rf" };

/** The refusals whose `name` is the daemon's English name of the radio `radio`. (`radio.name_taken`'s `name` is the name typed, and its `radio` is the other radio: it is not one of them.) */
const NAMES_A_RADIO: ReadonlySet<string> = new Set([
  "radio.last_enabled",
  "radio.no_line",
  "radio.no_modem",
  "radio.no_scope",
  "radio.no_setting",
  "radio.not_connected",
  "radio.off",
  "radio.type_kind",
  "radio.unknown",
]);

/** What some sentences list and the daemon does not send in `params`, from the lists the daemon has given the page. */
const LISTS: Params = {
  profiles: TNC_PROFILES.map((p) => p.key).join(", "),
  settings: CONFIG_KEYS.join(", "),
  forbidden: [...LIMITS.message.forbidden].join(" "),
  name_forbidden: [...LIMITS.object.nameForbidden].join(" "),
};

/** The values of a refusal with its radios as the page calls them: the `name` of the radio `radio` (and the word of its kind, `kind`, where the refusal says it), and the `holder` of a device by its id (`held_by`);
 * the GPS receiver (0), a radio the page does not know and a page that gives no radios keep the daemon's words. */
function radioParams(error: Failure, radios: RadioNames | undefined): Params {
  const params = error.params ?? {};
  const find = (id: string | number | undefined) => (radios !== undefined && typeof id === "number" && id > 0 ? radios.byId(id) : undefined);
  const radio = NAMES_A_RADIO.has(error.code ?? "") ? find(params.radio) : undefined;
  const holder = error.code === "radio.resource_held" ? find(params.held_by) : undefined;
  return {
    ...params,
    ...(radio === undefined ? {} : { name: radio.name }),
    ...(radio !== undefined && error.code === "radio.type_kind" ? { kind: t(KIND_WORDS[radio.kind]) } : {}),
    ...(holder === undefined ? {} : { holder: holder.name }),
  };
}

/** The id of the sentence the catalogue has for this refusal, or null. */
function idOf(error: Failure): MessageId | null {
  const id = `error.${error.code ?? "other"}`;
  return error.code !== "other" && hasMessage(id) ? id : null;
}

/** What is wrong, without the command and the setting in front: from the catalogue for a code it has, else the daemon's English words with those taken off the front. `radios`: the page's, by which a radio the
 * refusal names is said in the page's words. */
export function errorReason(error: Failure, radios?: RadioNames): string {
  const id = idOf(error);
  if (id) return t(id, { ...LISTS, ...radioParams(error, radios) });
  let text = error.text;
  if (error.cmd !== "" && text.startsWith(`${error.cmd}: `)) text = text.slice(error.cmd.length + 2);
  if (error.key !== null && text.startsWith(`${error.key}: `)) text = text.slice(error.key.length + 2);
  return text;
}

/** The line for a toast: the reason alone. The command's name (`send_message`, `set_config`) and the setting's key are the protocol's words, which say nothing to the person; the daemon's log has them. */
export function errorLine(error: Failure, radios?: RadioNames): string {
  return errorReason(error, radios);
}
