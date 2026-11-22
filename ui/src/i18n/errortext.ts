// What a refusal of the daemon (an `error` message) says to the person. The daemon sends a `code` and the `params` the sentence is made of (and the English `text`, which is the log's); the page says it in its own
// language from the catalogue (`error.<code>`, en/errors.ts). A refusal whose reason is another refusal's (nothing was sent, and why) carries the code of that reason as `why`, with its values: the page says it
// from `error.<why>` inside its own sentence, as `{reason}`. A code the page has no sentence for (a newer or an older daemon's, `other`) is said with the plain words of the place, by default `error.failed`: never
// the daemon's English and never the code. The page goes by `cmd`, `key` and `code`, never by the words of `text`. A refusal that names a radio by the daemon's English name (`name`, the holder of a device) carries
// that radio's id too (`radio`, `held_by`): given the page's radios (`useRadios()`), the sentence says the radio as the page calls it (lib/radios.ts `radioLabel`), in the page's language.
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
const KIND_WORDS: Record<PageRadio["kind"], MessageId> = { fm: "channel.fm", hf: "channel.hf", lora: "channel.lora" };

/** The refusals whose `name` is the daemon's English name of the radio `radio`. (`radio.name_taken`'s `name` is the name typed, and its `radio` is the other radio: it is not one of them.) */
const NAMES_A_RADIO: ReadonlySet<string> = new Set([
  "radio.last_enabled",
  "radio.not_taken",
  "radio.no_line",
  "radio.no_modem",
  "radio.no_scope",
  "radio.no_setting",
  "radio.not_connected",
  "radio.off",
  "radio.receive_only",
  "radio.type_kind",
  "radio.unknown",
  "status.too_long_for_radio",
]);

/** The port radio 1's search found last: told with the settings, and no setting of the operator's. */
const LAST_PORT = "serial/last_port";
/** What some sentences list and the daemon does not send in `params`, from the lists the daemon has given the page. */
const LISTS: Params = {
  profiles: TNC_PROFILES.map((p) => p.key).join(", "),
  settings: CONFIG_KEYS.filter((key) => key !== LAST_PORT).join(", "),
  forbidden: [...LIMITS.message.forbidden].join(" "),
  name_forbidden: [...LIMITS.object.nameForbidden].join(" "),
};

/** The values of a refusal with its radios as the page calls them: the `name` of the radio `radio` (and the word of its kind, `kind`, where the refusal says it), and the `holder` of a device by its id (`held_by`);
 * the GPS receiver (0), a radio the page does not know and a page that gives no radios keep the daemon's words. */
function radioParams(error: Failure, radios: RadioNames | undefined): Params {
  const params = error.params ?? {};
  const find = (id: string | number | undefined) =>
    radios !== undefined && typeof id === "number" && id > 0 ? radios.byId(id) : undefined;
  const radio = NAMES_A_RADIO.has(error.code ?? "") ? find(params.radio) : undefined;
  const holder = error.code === "radio.resource_held" ? find(params.held_by) : undefined;
  return {
    ...params,
    ...(radio === undefined ? {} : { name: radio.name }),
    ...(radio !== undefined && error.code === "radio.type_kind" ? { kind: t(KIND_WORDS[radio.kind]) } : {}),
    ...(holder === undefined ? {} : { holder: holder.name }),
  };
}

/** The id of the sentence the catalogue has for this code, or null. */
function idOf(code: string | undefined): MessageId | null {
  const id = `error.${code ?? "other"}`;
  return code !== undefined && code !== "other" && hasMessage(id) ? id : null;
}

/** The plain words of a refusal the catalogue has no sentence for. */
const failed = (): string => t("error.failed");

/** What is wrong, without the command and the setting in front, from the catalogue: the sentence of its code with its values, and the sentence of its `why` as its `{reason}`; `plain()` for a code it has no
 * sentence for. `radios`: the page's, by which a radio the refusal names is said in the page's words. */
export function errorReason(error: Failure, radios?: RadioNames, plain: () => string = failed): string {
  const id = idOf(error.code);
  if (id === null) return plain();
  const why = error.params?.["why"];
  if (typeof why !== "string") return t(id, { ...LISTS, ...radioParams(error, radios) });
  const inner = idOf(why);
  if (inner === null) return plain();
  const reason = t(inner, { ...LISTS, ...radioParams({ ...error, code: why }, radios) });
  return t(id, { ...radioParams(error, radios), reason });
}

/** The line for a toast: the reason alone. The command's name (`send_message`, `set_config`) and the setting's key are the protocol's words, which say nothing to the person; the daemon's log has them. */
export function errorLine(error: Failure, radios?: RadioNames): string {
  return errorReason(error, radios);
}
