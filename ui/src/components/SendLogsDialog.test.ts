// Send logs of the Help group: the button beside Download logs, the dialog it opens (one text, Send and Cancel, the page's dialog keys), what goes to the daemon (the page's info and the note, only when Send is pressed), the button in progress, and the one quiet
// line after it: the reference, or why it was not sent.
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SendLogsDialog from "@/components/SendLogsDialog.vue";
import SettingsHelp from "@/components/SettingsHelp.vue";
import { fakeDaemon, withDaemon } from "@/test/context";

const REF = "NEO-20261103-1015-7F3A";

/** The fetch of the page: `answer` is what the daemon says to the next request. */
function daemonSays(answer: () => Promise<Response>) {
  const fetcher = vi.fn((_input: RequestInfo | URL, _init?: RequestInit) => answer());
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

const json = (body: unknown, status = 200): Promise<Response> => Promise.resolve(new Response(JSON.stringify(body), { status }));
const dialog = (): HTMLElement | null => document.body.querySelector<HTMLElement>(".logsdialog");
const area = (): HTMLTextAreaElement => document.body.querySelector<HTMLTextAreaElement>(".logsdialog textarea") as HTMLTextAreaElement;
const button = (text: string): HTMLButtonElement =>
  [...document.body.querySelectorAll<HTMLButtonElement>(".logsdialog button")].find((b) => b.textContent?.trim() === text) as HTMLButtonElement;

let wrapper: VueWrapper;

function make(over = {}) {
  wrapper = mount(SettingsHelp, { global: withDaemon(fakeDaemon({ call: "OH2GBA", version: "0.16.1", ...over })), attachTo: document.body });
  return wrapper;
}

async function open() {
  await wrapper.get("#set-help-send").trigger("click");
  await flushPromises();
}

async function typeAndSend(note: string) {
  area().value = note;
  area().dispatchEvent(new Event("input", { bubbles: true }));
  button("Send").click();
  await flushPromises();
}

beforeEach(() => {
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
});
afterEach(() => {
  wrapper.unmount();
  document.body.innerHTML = "";
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("the Send logs button", () => {
  it("stands beside Download logs in the one row, before the one (i), and sends nothing by itself", () => {
    const fetcher = daemonSays(() => json({ ok: true, ref: REF }));
    make();
    const control = wrapper.get(".help-logs .field-control").element;
    expect([...control.children].map((c) => c.textContent?.trim())).toEqual(["Download logs", "Send logs", expect.any(String)]);
    expect(control.lastElementChild?.classList.contains("infotip")).toBe(true);
    expect(wrapper.get("#set-help-send").classes()).toEqual(["btn"]);
    expect(wrapper.findAll(".action-row")).toHaveLength(1);
    expect(fetcher).not.toHaveBeenCalled();
  });
});

describe("the dialog", () => {
  it("opens over the page with one text, What happened?, a few lines and at most 2000 characters, and Send and Cancel; the focus is in the text", async () => {
    make();
    expect(dialog()).toBeNull();
    await open();
    const box = dialog();
    expect(box?.getAttribute("role")).toBe("dialog");
    expect(box?.getAttribute("aria-modal")).toBe("true");
    expect(box?.querySelector("h2")?.textContent).toBe("Send logs");
    const label = box?.querySelector("label");
    expect(label?.textContent).toBe("What happened?");
    expect(label?.getAttribute("for")).toBe(area().id);
    expect(Number(area().getAttribute("rows"))).toBeGreaterThanOrEqual(4);
    expect(area().getAttribute("maxlength")).toBe("2000");
    expect(area().value).toBe("");
    expect(document.activeElement).toBe(area());
    expect(box?.parentElement?.parentElement).toBe(document.body);
  });

  it("has nothing but the one text and the buttons Send (the filled one) and Cancel", async () => {
    make();
    await open();
    const box = dialog();
    expect([...(box?.querySelectorAll("textarea") ?? [])]).toHaveLength(1);
    expect([...(box?.querySelectorAll(".logsdialog-foot button") ?? [])].map((b) => b.textContent?.trim())).toEqual(["Send", "Cancel"]);
    expect(box?.querySelector(".logsdialog-foot .btn.primary")?.textContent).toBe("Send");
  });

  it("has an (i) that says what goes and that nothing goes before Send, and no other line of explanation", async () => {
    make();
    await open();
    expect(dialog()?.querySelectorAll("p")).toHaveLength(0);
    (dialog()?.querySelector(".infotip button") as HTMLButtonElement).click();
    await flushPromises();
    expect([...(dialog()?.querySelectorAll(".info-line") ?? [])].map((line) => line.textContent)).toEqual([
      "Sends the logs, the settings without the access key and the packets heard and sent to the project, with your words.",
      "Nothing is sent before you press Send.",
    ]);
  });

  it.each([
    ["Cancel", () => button("Cancel").click()],
    ["the cross", () => (dialog()?.querySelector(".xbtn") as HTMLButtonElement).click()],
    ["Esc", () => dialog()?.parentElement?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }))],
    ["a press beside it", () => dialog()?.parentElement?.dispatchEvent(new Event("pointerdown", { bubbles: true }))],
  ])("is closed by %s and sends nothing, and the focus goes back to the button", async (_name, close) => {
    const fetcher = daemonSays(() => json({ ok: true, ref: REF }));
    make();
    await open();
    area().value = "words that stay unsent";
    area().dispatchEvent(new Event("input", { bubbles: true }));
    close();
    await flushPromises();
    expect(dialog()).toBeNull();
    expect(fetcher).not.toHaveBeenCalled();
    expect(wrapper.get(".help-result").text()).toBe("");
    expect(document.activeElement).toBe(wrapper.get("#set-help-send").element);
    expect(wrapper.get("#set-help-send").attributes("disabled")).toBeUndefined();
  });

  it("keeps Tab inside it", async () => {
    make();
    await open();
    const last = button("Cancel");
    last.focus();
    const event = new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true });
    last.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
    expect(dialog()?.contains(document.activeElement)).toBe(true);
  });

  it("emits the words with the blanks round them taken off, and nothing else", async () => {
    const standalone = mount(SendLogsDialog, { props: { opener: null }, global: withDaemon(), attachTo: document.body });
    await standalone.get("textarea").setValue("  It stopped.\nTwo lines.  \n");
    await standalone.get(".btn.primary").trigger("click");
    expect(standalone.emitted("send")).toEqual([["It stopped.\nTwo lines."]]);
    standalone.unmount();
  });
});

describe("sending", () => {
  it("posts the page's info and the note to the daemon, and the button reads Sending… in its place until the answer, with both buttons off", async () => {
    let answer: (response: Response) => void = () => undefined;
    const fetcher = daemonSays(() => new Promise<Response>((resolve) => (answer = resolve)));
    make({ connection: "open" });
    await open();
    await typeAndSend("It stopped beaconing.");
    expect(dialog()).toBeNull();
    expect(fetcher).toHaveBeenCalledTimes(1);
    const [url, init] = fetcher.mock.calls[0] ?? [];
    expect(url).toBe("http://127.0.0.1:7303/support/send");
    expect(init).toMatchObject({ method: "POST", credentials: "same-origin" });
    const body = JSON.parse(typeof init?.body === "string" ? init.body : "") as { page: Record<string, unknown>; note: string };
    expect(Object.keys(body).sort()).toEqual(["note", "page"]);
    expect(body.note).toBe("It stopped beaconing.");
    expect(body.page).toMatchObject({ daemonVersion: "0.16.1", connection: "open" });
    const send = wrapper.get("#set-help-send");
    expect(send.text()).toBe("Sending…");
    expect(send.attributes("disabled")).toBeDefined();
    expect(wrapper.get("#set-help-logs").text()).toBe("Download logs");
    expect(wrapper.get("#set-help-logs").attributes("disabled")).toBeDefined();
    expect(wrapper.get(".help-result").text()).toBe("");
    answer(new Response(JSON.stringify({ ok: true, ref: REF }), { status: 200 }));
    await flushPromises();
    expect(send.text()).toBe("Send logs");
    expect(send.attributes("disabled")).toBeUndefined();
    expect(wrapper.get("#set-help-logs").attributes("disabled")).toBeUndefined();
  });

  it("says Sent with the reference in one quiet line", async () => {
    daemonSays(() => json({ ok: true, ref: REF }));
    make();
    await open();
    await typeAndSend("x");
    expect(wrapper.get(".help-result .muted").text()).toBe(`Sent. Reference ${REF}.`);
    expect(wrapper.find(".help-result .field-error").exists()).toBe(false);
    expect(wrapper.findAll(".help-result p")).toHaveLength(1);
  });

  it("sends an empty note when nothing was written", async () => {
    const fetcher = daemonSays(() => json({ ok: true, ref: REF }));
    make();
    await open();
    await typeAndSend("");
    const sent = fetcher.mock.calls[0]?.[1]?.body;
    expect((JSON.parse(typeof sent === "string" ? sent : "") as { note: string }).note).toBe("");
  });

  it.each([
    [() => json({ ok: false, reason: "offline" }), "Not sent: no internet connection."],
    [() => json({ ok: false, reason: "refused" }), "Not sent: the server refused it."],
    [() => json({ ok: false, reason: "rate" }), "Not sent: too many sends just now. Try again later."],
    [() => json({ ok: false, reason: "too_large" }), "Not sent: the logs are too large."],
    [() => json({ ok: false, reason: "something new" }), "Not sent: the server refused it."],
    [() => Promise.resolve(new Response(null, { status: 401 })), "No access: reload the page, enter the access key and try again."],
    [() => Promise.resolve(new Response(null, { status: 429 })), "Another file is being made. Try again in a minute."],
    [() => Promise.resolve(new Response(null, { status: 500 })), "The file could not be made (error 500)."],
    [() => Promise.reject(new TypeError("network")), "The daemon could not be reached."],
  ])("says the reason in plain words when it was not sent (%#)", async (answer, text) => {
    daemonSays(answer);
    make();
    await open();
    await typeAndSend("x");
    expect(wrapper.get(".help-result .field-error").text()).toBe(text);
    expect(wrapper.find(".help-result .muted").exists()).toBe(false);
    expect(wrapper.get("#set-help-send").text()).toBe("Send logs");
    expect(wrapper.get("#set-help-send").attributes("disabled")).toBeUndefined();
  });

  it("takes the words of an earlier outcome back at the next try, and a download takes the sent line back", async () => {
    daemonSays(() => json({ ok: false, reason: "offline" }));
    make();
    await open();
    await typeAndSend("x");
    expect(wrapper.find(".help-result .field-error").exists()).toBe(true);
    daemonSays(() => json({ ok: true, ref: REF }));
    await open();
    await typeAndSend("y");
    expect(wrapper.find(".help-result .field-error").exists()).toBe(false);
    expect(wrapper.get(".help-result .muted").text()).toContain(REF);
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:support"), revokeObjectURL: vi.fn() }));
    daemonSays(() => Promise.resolve(new Response("PK", { status: 200, headers: { "Content-Disposition": 'attachment; filename="f.zip"' } })));
    await wrapper.get("#set-help-logs").trigger("click");
    await flushPromises();
    expect(wrapper.get(".help-result .muted").text()).toBe("Saved f.zip.");
    expect(wrapper.text()).not.toContain(REF);
  });
});
