// The page's end of the login a device on the network goes through (neoaprs/web/access.py):
// `probe` asks whether this device is let in, `login` sends the access key and `renewKey` asks
// for a new one. The daemon answers 204 for yes, 401 for not logged in, 403 for a wrong key and
// 429 while this address is shut out; the session is a cookie the browser keeps, so nothing
// here stores anything. `keyLink` writes the address with the key that the Settings, Web page
// code holds (`#key=...`), and `takeKey` reads the key a phone brings in it: the fragment never
// reaches the daemon, and it is removed from the address bar and history at once.
import { t } from "@/i18n";

/**
 * The start of the fragment that carries the access key in the address the phone code holds.
 */
const KEY_FRAGMENT = "#key=";
/**
 * The longest key the daemon reads (a longer one is refused as no key at all,
 * neoaprs/web/access.py).
 */
const KEY_MOST = 64;

type Access = "open" | "locked";

export function endpoint(path: string): string {
  return new URL(path, document.baseURI).toString();
}

/**
 * The page's address with the access key after `#`, as the phone code holds it and `takeKey`
 * reads it; "" while there is no address or no key.
 */
export function keyLink(url: string, key: string): string {
  return url !== "" && key !== "" ? `${url}${KEY_FRAGMENT}${encodeURIComponent(key)}` : "";
}

/**
 * The key in the address's fragment `#key=...`, cut to the length the daemon reads, or "" for
 * any other fragment (the app window's `#app` is left alone). The fragment is removed from the
 * address and this history entry whether the key is good or not, so it is in no bookmark, icon
 * or kept tab.
 */
export function takeKey(loc: Location = location, hist: History = history): string {
  const hash = loc.hash;
  if (!hash.startsWith(KEY_FRAGMENT)) return "";
  hist.replaceState(hist.state, "", loc.pathname + loc.search);
  const raw = hash.slice(KEY_FRAGMENT.length);
  let key = raw;
  try {
    key = decodeURIComponent(raw);
  } catch {
    // A stray % is no escape: the text is the key as it was typed.
  }
  return key.slice(0, KEY_MOST);
}

/**
 * Whether this device is let in. Only a 401 says no: any other answer, or none, leaves the page
 * to show what it cannot reach.
 */
export async function probe(fetcher: typeof fetch = fetch): Promise<Access> {
  try {
    return (await fetcher(endpoint("access"), { cache: "no-store" })).status === 401 ? "locked" : "open";
  } catch {
    return "open";
  }
}

async function post(path: string, body: string | undefined, fetcher: typeof fetch): Promise<number> {
  try {
    return (await fetcher(endpoint(path), { method: "POST", body, cache: "no-store" })).status;
  } catch {
    return 0;
  }
}

/** Send the key; "" when the device is let in, else what to tell the person. */
export async function login(key: string, fetcher: typeof fetch = fetch): Promise<string> {
  const status = await post("access", JSON.stringify({ key }), fetcher);
  if (status === 204) return "";
  if (status === 403) return t("settings.access.wrong");
  return status === 429 ? t("settings.access.shut_out") : t("settings.no_answer");
}

/**
 * Ask for a new key, which logs every other device out; "" when it was made, else what went
 * wrong.
 */
export async function renewKey(fetcher: typeof fetch = fetch): Promise<string> {
  const status = await post("access/new", undefined, fetcher);
  return status === 204 ? "" : t("settings.no_answer");
}
