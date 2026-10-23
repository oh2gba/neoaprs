// The page's end of the login a device on the network goes through (neoaprs/web/access.py): `probe` asks whether this device is let in, `login` sends the access key and `renewKey` asks for a new one. The
// daemon answers 204 for yes, 401 for not logged in, 403 for a wrong key and 429 while this address is shut out; the session is a cookie the browser keeps, so nothing here stores anything.
type Access = "open" | "locked";

const WRONG = "Wrong key.";
const SHUT_OUT = "Too many tries. Wait a few minutes.";
const NO_ANSWER = "No answer from the daemon.";

function endpoint(path: string): string {
  return new URL(path, document.baseURI).toString();
}

/** Is this device let in? Only a 401 says no: any other answer, or none, leaves the page to show what it cannot reach. */
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

/** Sends the key; "" when the device is let in, else what to tell the person. */
export async function login(key: string, fetcher: typeof fetch = fetch): Promise<string> {
  const status = await post("access", JSON.stringify({ key }), fetcher);
  if (status === 204) return "";
  if (status === 403) return WRONG;
  return status === 429 ? SHUT_OUT : NO_ANSWER;
}

/** Asks for a new key, which logs every other device out; "" when it was made, else what went wrong. */
export async function renewKey(fetcher: typeof fetch = fetch): Promise<string> {
  const status = await post("access/new", undefined, fetcher);
  return status === 204 ? "" : NO_ANSWER;
}
