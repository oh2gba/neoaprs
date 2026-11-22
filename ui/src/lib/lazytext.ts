// An object with some words that are made when read, not when the module is loaded: `lazyText({
// value: "off" }, { label: () => t("...") })` has the `label` in the language the page has when
// it is asked, and a template that reads it is drawn again when the language changes (`t` reads
// the reactive locale). A text kept in a constant would stay in the language it was made in.

/**
 * `plain` with the fields of `words` added as getters (they are enumerable, and a spread copies
 * them as the text they are then).
 */
export function lazyText<T extends object, K extends string>(
  plain: T,
  words: Readonly<Record<K, () => string>>,
): T & Readonly<Record<K, string>> {
  const made = { ...plain };
  for (const key of Object.keys(words) as K[]) Object.defineProperty(made, key, { enumerable: true, get: words[key] });
  return made as T & Readonly<Record<K, string>>;
}
