// A query the operator writes in the station panel of the Stations tab (the custom query; the daemon's command `query` with `custom`), held to the rule the daemon holds it to (neoaprs/message.py, `query_text`): after the
// spaces at its ends are taken off it begins with "?" and says something after it, is printable ASCII without | ~ { (a { would begin a message id, and a query has none) and fits in the text of a message, 67 characters
// (LIMITS.message, which the daemon's protocol gives). It goes on the air upper-cased, as the specification's queries and the calls in them are.
import { LIMITS } from "@/protocol/lists";

/** What is wrong with a query: it is no query ("?" and something after it), it is too long, or it has a character a query cannot carry. */
export type QueryProblem = "form" | "long" | "chars";

/** The query as it is sent, or what is wrong with it. */
export function customQuery(text: string): { text: string } | { problem: QueryProblem } {
  const query = text.trim();
  if (query.length < 2 || !query.startsWith("?")) return { problem: "form" };
  if (query.length > LIMITS.message.textMax) return { problem: "long" };
  if ([...query].some((c) => c < " " || c > "~" || LIMITS.message.forbidden.includes(c))) return { problem: "chars" };
  return { text: query.toUpperCase() };
}

/** The most characters a query has: the box takes no more. */
export const QUERY_MAX = LIMITS.message.textMax;
