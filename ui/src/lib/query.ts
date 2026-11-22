// A query the operator writes in the station panel of the Stations tab (the custom query; the
// daemon's command `query` with `custom`), held to the daemon's rule (neoaprs/message.py
// `query_text`): after leading and trailing spaces are removed it begins with "?" and says
// something after it, is printable ASCII without | ~ { (a { would begin a message id, and a
// query has none) and fits in the text of a message, 67 characters (LIMITS.message). It goes on
// the air upper-cased, as the specification's queries and the calls in them are.
import { textRefusal } from "@/lib/recipients";
import { LIMITS } from "@/protocol/lists";

/**
 * What is wrong with a query: it is no query ("?" and something after it), it is too long, or it
 * has a character a query cannot carry.
 */
export type QueryProblem = "form" | "long" | "chars";

/** The query as it is sent, or what is wrong with it. */
export function customQuery(text: string): { text: string } | { problem: QueryProblem } {
  const query = text.trim();
  if (query.length < 2 || !query.startsWith("?")) return { problem: "form" };
  if (query.length > LIMITS.message.textMax) return { problem: "long" };
  if (textRefusal(query) !== null) return { problem: "chars" };
  return { text: query.toUpperCase() };
}

/** The most characters a query has: the box takes no more. */
export const QUERY_MAX = LIMITS.message.textMax;
