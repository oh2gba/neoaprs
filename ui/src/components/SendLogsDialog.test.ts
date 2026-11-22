// Send feedback / logs of the Help group: the group's one button, the dialog it opens (one text,
// the logs file under it, Send and Cancel, the page's dialog keys), what goes to the daemon (the
// page info and the note, only on Send), the button in progress, and the one quiet line after it
// (the reference, or why it was not sent). The file row: its name downloads the file as Download
// logs does, its × takes the file off so that the words go alone (Send is then off without words),
// Attach puts it back, and nothing in the dialog moves. The group keeps what the dialog holds until
// a send worked; the downloaded file is named by the Send of that opening and by a retry after a
// failure, and forgotten when the dialog is closed with nothing sent. The row's words exist in nine
// languages; no line explains.
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ref, shallowRef } from "vue";
import SendLogsDialog from "@/components/SendLogsDialog.vue";
import SettingsAbout from "@/components/SettingsAbout.vue";
import SettingsHelp from "@/components/SettingsHelp.vue";
import { LOCALES } from "@/i18n/locales";
import { fakeDaemon, withDaemon } from "@/test/context";
import { cssRule, mediaRule } from "@/test/css";

const REF = "NEO-20261103-1015-7F3A";

/** The fetch of the page: `answer` is what the daemon says to the next request. */
function daemonSays(answer: () => Promise<Response>) {
  const fetcher = vi.fn((_input: RequestInfo | URL, _init?: RequestInit) => answer());
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

const json = (body: unknown, status = 200): Promise<Response> => Promise.resolve(new Response(JSON.stringify(body), { status }));
const NAME = "neoaprs-support-OH2GBA.zip";
const MADE = "neoaprs-support-OH2GBA-20261021-123456Z.zip";
const zip = (): Promise<Response> =>
  Promise.resolve(new Response("PK", { status: 200, headers: { "Content-Type": "application/zip", "Content-Disposition": `attachment; filename="${MADE}"` } }));

const address = (input: RequestInfo | URL | undefined): string => (typeof input === "string" ? input : input instanceof URL ? input.href : (input?.url ?? ""));

/**
 * The fetch of the page with the daemon's two routes: `bundle` answers Download logs, `send` the
 * dialog's Send.
 */
function daemonRoutes(bundle: () => Promise<Response> = zip, send: () => Promise<Response> = () => json({ ok: true, ref: REF })) {
  return daemonSays(() => Promise.reject(new Error("unused"))).mockImplementation((input) => (address(input).endsWith("/support/bundle") ? bundle() : send()));
}

/** What a request of the page carried: the address, the method and the rest, and the body read. */
function asked(call: [RequestInfo | URL, RequestInit?] | undefined) {
  const [url, init] = call ?? [];
  const body = JSON.parse(typeof init?.body === "string" ? init.body : "{}") as { page: Record<string, unknown>; note?: string; file?: unknown };
  return { url: address(url), method: init?.method, headers: init?.headers, credentials: init?.credentials, cache: init?.cache, body };
}

const row = (): HTMLElement => document.body.querySelector<HTMLElement>(".logsdialog-attached") as HTMLElement;
const fileName = (): HTMLButtonElement => row().querySelector<HTMLButtonElement>(".logsdialog-file") as HTMLButtonElement;
const toggle = (): HTMLButtonElement => row().querySelector<HTMLButtonElement>(".logsdialog-x") as HTMLButtonElement;
const statusLine = (): HTMLElement => document.body.querySelector<HTMLElement>(".logsdialog-status") as HTMLElement;
/** The face of the × that is shown: "×" or "Attach". */
const face = (): string | undefined => toggle().querySelector(".twowords > span:not(.twowords-off)")?.textContent?.trim();
const downloads: { href: string; download: string }[] = [];

async function write(text: string) {
  area().value = text;
  area().dispatchEvent(new Event("input", { bubbles: true }));
  await flushPromises();
}

async function press(control: HTMLElement) {
  control.click();
  await flushPromises();
}
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
  downloads.length = 0;
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:support"), revokeObjectURL: vi.fn() }));
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    downloads.push({ href: this.href, download: this.download });
  });
});
afterEach(() => {
  wrapper.unmount();
  document.body.innerHTML = "";
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("the Send feedback button", () => {
  it("is the group's one button, the primary one, before the one (i), and sends nothing by itself; Download logs is About's", () => {
    const fetcher = daemonSays(() => json({ ok: true, ref: REF }));
    make();
    const control = wrapper.get(".help-logs .field-control").element;
    expect([...control.children].map((c) => c.textContent?.trim())).toEqual(["Send feedback / logs", expect.any(String)]);
    expect(control.lastElementChild?.classList.contains("infotip")).toBe(true);
    expect(wrapper.get("#set-help-send").classes()).toEqual(["btn", "primary"]);
    expect(wrapper.find("#set-help-logs").exists()).toBe(false);
    expect(wrapper.findAll(".action-row")).toHaveLength(1);
    expect(fetcher).not.toHaveBeenCalled();
  });
});

describe("the dialog", () => {
  it("opens over the page with one text, Your message, a few lines and at most 2000 characters, and Send and Cancel; the focus is in the text", async () => {
    make();
    expect(dialog()).toBeNull();
    await open();
    const box = dialog();
    expect(box?.getAttribute("role")).toBe("dialog");
    expect(box?.getAttribute("aria-modal")).toBe("true");
    expect(box?.querySelector("h2")?.textContent).toBe("Send feedback / logs");
    const label = box?.querySelector("label");
    expect(label?.textContent).toBe("Your message");
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

  it("shows the logs file attached under the text, and has no (i) and no line that explains", async () => {
    make();
    await open();
    const box = dialog() as HTMLElement;
    expect([...box.children].map((part) => part.tagName.toLowerCase())).toEqual(["header", "label", "textarea", "div", "p", "footer"]);
    expect(box.querySelector(".infotip")).toBeNull();
    expect([...box.querySelectorAll("p")].map((line) => [line.className, line.textContent?.trim()])).toEqual([["logsdialog-status", ""]]);
    expect(row().getAttribute("role")).toBe("group");
    expect(row().getAttribute("aria-label")).toBe("Attached");
    expect(fileName().textContent?.trim()).toBe(NAME);
    expect(box.textContent).not.toMatch(/access key|Nothing is sent|before you press/i);
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
    const download = { running: ref(false), saved: shallowRef<string | null>(null), problem: ref(""), collect: vi.fn(() => Promise.resolve()) };
    const standalone = mount(SendLogsDialog, { props: { opener: null, download }, attachTo: document.body });
    await standalone.get("textarea").setValue("  It stopped.\nTwo lines.  \n");
    await standalone.get(".btn.primary").trigger("click");
    expect(standalone.emitted("send")).toEqual([["It stopped.\nTwo lines.", true]]);
    expect(standalone.emitted("attached")).toBeUndefined();
    expect(download.collect).not.toHaveBeenCalled();
    standalone.unmount();
  });
});

describe("sending", () => {
  it("posts the page's info and the note to the daemon, and the button reads Sending… in its place and is off until the answer", async () => {
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
    expect(wrapper.get(".help-result").text()).toBe("");
    answer(new Response(JSON.stringify({ ok: true, ref: REF }), { status: 200 }));
    await flushPromises();
    expect(send.text()).toBe("Send feedback / logs");
    expect(send.attributes("disabled")).toBeUndefined();
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

  it("sends an empty note with the file when nothing was written", async () => {
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
    [() => Promise.reject(new TypeError("network")), "NeoAPRS could not be reached."],
  ])("says the reason in plain words when it was not sent (%#)", async (answer, text) => {
    daemonSays(answer);
    make();
    await open();
    await typeAndSend("x");
    expect(wrapper.get(".help-result .field-error").text()).toBe(text);
    expect(wrapper.find(".help-result .muted").exists()).toBe(false);
    expect(wrapper.get("#set-help-send").text()).toBe("Send feedback / logs");
    expect(wrapper.get("#set-help-send").attributes("disabled")).toBeUndefined();
  });

  it("takes the words of an earlier outcome back at the next try", async () => {
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
  });

  it("keeps the words written when they were not sent, and forgets them once they were", async () => {
    daemonSays(() => json({ ok: false, reason: "offline" }));
    make();
    await open();
    await typeAndSend("The beacon stopped at 10:15.");
    await open();
    expect(area().value).toBe("The beacon stopped at 10:15.");
    daemonSays(() => json({ ok: true, ref: REF }));
    button("Send").click();
    await flushPromises();
    await open();
    expect(area().value).toBe("");
  });
});

describe("the file's row", () => {
  it("is the file's name, a link that downloads it, and a small × that takes it off, named for a screen reader as the × of a hop is", async () => {
    make();
    await open();
    expect([...row().children].map((part) => part.tagName.toLowerCase())).toEqual(["svg", "button", "button"]);
    expect(row().querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
    expect(fileName().classList.contains("linkbtn")).toBe(true);
    expect(fileName().disabled).toBe(false);
    expect(fileName().getAttribute("aria-label")).toBe(`Download ${NAME}`);
    expect(fileName().title).toBe(`Download ${NAME}`);
    expect(face()).toBe("×");
    expect(toggle().getAttribute("aria-label")).toBe(`Remove ${NAME}`);
    expect(toggle().title).toBe(`Remove ${NAME}`);
    expect(dialog()?.textContent).not.toMatch(/\d\s?(KB|MB)/); // (no size: the page shows the size of no file)
  });

  it("names the file nocall without a call", async () => {
    make({ call: null });
    await open();
    expect(fileName().textContent?.trim()).toBe("neoaprs-support-nocall.zip");
  });

  it("downloads by its name what Download logs downloads: the same request to the daemon, saved the same way under the daemon's name", async () => {
    const fetcher = daemonRoutes();
    make({ connection: "open" });
    const about = mount(SettingsAbout, { global: withDaemon(fakeDaemon({ call: "OH2GBA", version: "0.16.1", connection: "open" })) });
    await about.get("#set-help-logs").trigger("click");
    await flushPromises();
    await open();
    await press(fileName());
    expect(fetcher).toHaveBeenCalledTimes(2);
    const [fromAbout, fromDialog] = fetcher.mock.calls.map(asked);
    expect(fromDialog?.url).toBe("http://127.0.0.1:7303/support/bundle");
    const same = (request: typeof fromAbout) => ({ ...request, body: { ...request?.body, page: { ...request?.body.page, time: "", timeMs: 0 } } });
    expect(same(fromDialog)).toEqual(same(fromAbout));
    expect(Object.keys(fromDialog?.body ?? {})).toEqual(["page"]);
    expect(downloads).toEqual([
      { href: "blob:support", download: MADE },
      { href: "blob:support", download: MADE },
    ]);
    expect(statusLine().textContent?.trim()).toBe(`Saved ${MADE}.`);
    expect(statusLine().querySelector(".field-error")).toBeNull();
    expect(dialog()).not.toBeNull();
    about.unmount();
  });

  it("says Collecting… under the file while it is made, with the name as it was, and Send waits; it asks once", async () => {
    let finish: (response: Response) => void = () => undefined;
    const fetcher = daemonRoutes(() => new Promise<Response>((resolve) => (finish = resolve)));
    make();
    await open();
    await write("words");
    await press(fileName());
    expect(statusLine().textContent?.trim()).toBe("Collecting…");
    expect(fileName().textContent?.trim()).toBe(NAME);
    expect(fileName().disabled).toBe(true);
    expect(fileName().getAttribute("aria-busy")).toBe("true");
    expect(button("Send").disabled).toBe(true);
    await press(fileName());
    expect(fetcher).toHaveBeenCalledTimes(1);
    finish(await zip());
    await flushPromises();
    expect(fileName().disabled).toBe(false);
    expect(button("Send").disabled).toBe(false);
    expect(statusLine().textContent?.trim()).toBe(`Saved ${MADE}.`);
  });

  it("has Send name the file that was downloaded, so that the daemon sends that very one", async () => {
    const fetcher = daemonRoutes();
    make();
    await open();
    await press(fileName());
    await typeAndSend("I looked inside.");
    const sent = asked(fetcher.mock.calls[1]);
    expect(sent.url).toBe("http://127.0.0.1:7303/support/send");
    expect(Object.keys(sent.body).sort()).toEqual(["file", "note", "page"]);
    expect(sent.body.file).toBe(MADE);
    expect(sent.body.note).toBe("I looked inside.");
  });

  it("names the downloaded file again at the next try when the send failed, and no file once one was sent", async () => {
    const fetcher = daemonRoutes(zip, () => json({ ok: false, reason: "offline" }));
    make();
    await open();
    await press(fileName());
    await typeAndSend("x");
    await open();
    // the file that goes is still the one that was saved
    expect(statusLine().textContent?.trim()).toBe(`Saved ${MADE}.`);
    fetcher.mockImplementation(() => json({ ok: true, ref: REF }));
    await press(button("Send"));
    expect(asked(fetcher.mock.calls[2]).body.file).toBe(MADE);
    await open();
    expect(statusLine().textContent?.trim()).toBe("");
    await typeAndSend("y");
    expect(Object.keys(asked(fetcher.mock.calls[3]).body).sort()).toEqual(["note", "page"]);
  });

  it.each([
    ["Cancel", () => button("Cancel").click()],
    ["Esc", () => dialog()?.parentElement?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }))],
  ])(
    "forgets the downloaded file when it is closed by %s with nothing sent: the next opening does not say Saved, and Send sends the logs as they are then",
    async (_name, close) => {
      const fetcher = daemonRoutes();
      make();
      await open();
      await write("words that stay");
      await press(fileName());
      expect(statusLine().textContent?.trim()).toBe(`Saved ${MADE}.`);
      close();
      await flushPromises();
      expect(dialog()).toBeNull();
      await open();
      expect(statusLine().textContent?.trim()).toBe("");
      expect(area().value).toBe("words that stay");
      await press(button("Send"));
      // no name: the daemon makes the file now
      expect(Object.keys(asked(fetcher.mock.calls[1]).body).sort()).toEqual(["note", "page"]);
    },
  );

  it("does not name a download that ended after the dialog was closed; one that still runs at the next opening is named when it ends there", async () => {
    let finish: (response: Response) => void = () => undefined;
    const fetcher = daemonRoutes(() => new Promise<Response>((resolve) => (finish = resolve)));
    make();
    await open();
    await press(fileName());
    await press(button("Cancel"));
    expect(dialog()).toBeNull();
    await open();
    expect(statusLine().textContent?.trim()).toBe("Collecting…");
    expect(button("Send").disabled).toBe(true);
    await press(button("Cancel"));
    finish(await zip());
    await flushPromises();
    expect(downloads).toEqual([{ href: "blob:support", download: MADE }]); // (the file is saved all the same)
    await open();
    expect(statusLine().textContent?.trim()).toBe("");
    await press(fileName());
    await press(button("Cancel"));
    await open();
    expect(statusLine().textContent?.trim()).toBe("Collecting…");
    finish(await zip());
    await flushPromises();
    expect(statusLine().textContent?.trim()).toBe(`Saved ${MADE}.`);
    fetcher.mockImplementation(() => json({ ok: true, ref: REF }));
    await typeAndSend("I looked inside.");
    expect(asked(fetcher.mock.calls[2]).body.file).toBe(MADE);
  });

  it("keeps the file off at the next opening after Cancel, and Attach there puts back a file that is made at the send", async () => {
    const fetcher = daemonRoutes();
    make();
    await open();
    await press(fileName());
    await press(toggle());
    await press(button("Cancel"));
    await open();
    expect(row().classList.contains("off")).toBe(true);
    expect(statusLine().textContent?.trim()).toBe("");
    await press(toggle());
    await typeAndSend("x");
    expect(Object.keys(asked(fetcher.mock.calls[1]).body).sort()).toEqual(["note", "page"]);
  });

  it("names the file of the earlier download when a later one failed: the daemon still holds that one", async () => {
    const fetcher = daemonRoutes();
    make();
    await open();
    await press(fileName());
    fetcher.mockImplementation(() => Promise.resolve(new Response(null, { status: 429 })));
    await press(fileName());
    expect(statusLine().querySelector(".field-error")?.textContent).toBe("Another file is being made. Try again in a minute.");
    fetcher.mockImplementation(() => json({ ok: true, ref: REF }));
    await typeAndSend("x");
    expect(asked(fetcher.mock.calls[2]).body.file).toBe(MADE);
  });

  it("does not say again at the next opening why a download failed", async () => {
    daemonRoutes(() => Promise.resolve(new Response(null, { status: 500 })));
    make();
    await open();
    await press(fileName());
    expect(statusLine().querySelector(".field-error")).not.toBeNull();
    await press(button("Cancel"));
    await open();
    expect(statusLine().textContent?.trim()).toBe("");
  });

  it.each([
    [() => Promise.resolve(new Response(null, { status: 401 })), "No access: reload the page, enter the access key and try again."],
    [() => Promise.resolve(new Response(null, { status: 429 })), "Another file is being made. Try again in a minute."],
    [() => Promise.resolve(new Response(null, { status: 500 })), "The file could not be made (error 500)."],
    [() => Promise.reject(new TypeError("network")), "NeoAPRS could not be reached."],
  ])("says under the file why it could not be downloaded, stays open, and Send still sends (%#)", async (answer, text) => {
    const fetcher = daemonRoutes(answer);
    make();
    await open();
    await press(fileName());
    expect(statusLine().querySelector(".field-error")?.textContent).toBe(text);
    expect(downloads).toEqual([]);
    expect(dialog()).not.toBeNull();
    expect(wrapper.get(".help-result").text()).toBe("");
    await typeAndSend("x");
    expect(Object.keys(asked(fetcher.mock.calls[1]).body).sort()).toEqual(["note", "page"]);
    expect(wrapper.get(".help-result .muted").text()).toBe(`Sent. Reference ${REF}.`);
  });
});

describe("the × of the file", () => {
  it("takes the file off: the name stays, dimmed and no link, the × reads Attach, and Send sends the words alone", async () => {
    const fetcher = daemonRoutes();
    make();
    await open();
    await write("Thanks for the HF mode.");
    await press(toggle());
    expect(row().classList.contains("off")).toBe(true);
    expect(row().getAttribute("aria-label")).toBeNull();
    expect(fileName().textContent?.trim()).toBe(NAME);
    expect(fileName().disabled).toBe(true);
    expect(fileName().getAttribute("aria-label")).toBeNull();
    expect(fileName().title).toBe("");
    expect(face()).toBe("Attach");
    expect(toggle().getAttribute("aria-label")).toBeNull();
    expect(toggle().title).toBe("");
    await press(fileName());
    expect(fetcher).not.toHaveBeenCalled();
    await press(button("Send"));
    expect(dialog()).toBeNull();
    expect(fetcher).toHaveBeenCalledTimes(1);
    const sent = asked(fetcher.mock.calls[0]);
    expect(sent.url).toBe("http://127.0.0.1:7303/support/send");
    expect(sent.body.file).toBe(false);
    expect(sent.body.note).toBe("Thanks for the HF mode.");
    expect(wrapper.get(".help-result .muted").text()).toBe(`Sent. Reference ${REF}.`);
  });

  it("leaves Send off until something is written, and blanks are nothing", async () => {
    const fetcher = daemonRoutes();
    make();
    await open();
    expect(button("Send").disabled).toBe(false);
    await press(toggle());
    expect(button("Send").disabled).toBe(true);
    await write("  \n ");
    expect(button("Send").disabled).toBe(true);
    await press(button("Send"));
    expect(dialog()).not.toBeNull();
    expect(fetcher).not.toHaveBeenCalled();
    await write("a word");
    expect(button("Send").disabled).toBe(false);
    await write("");
    expect(button("Send").disabled).toBe(true);
    expect(dialog()?.querySelectorAll("p")).toHaveLength(1); // (no sentence says why)
    expect(statusLine().textContent?.trim()).toBe("");
  });

  it("puts the file back with Attach, and Send sends it again", async () => {
    const fetcher = daemonRoutes();
    make();
    await open();
    await press(toggle());
    await press(toggle());
    expect(row().classList.contains("off")).toBe(false);
    expect(face()).toBe("×");
    expect(fileName().disabled).toBe(false);
    expect(row().getAttribute("aria-label")).toBe("Attached");
    expect(button("Send").disabled).toBe(false);
    await typeAndSend("");
    expect(Object.keys(asked(fetcher.mock.calls[0]).body).sort()).toEqual(["note", "page"]);
  });

  it("keeps the focus on itself when pressed, either way", async () => {
    make();
    await open();
    toggle().focus();
    await press(toggle());
    expect(document.activeElement).toBe(toggle());
    await press(toggle());
    expect(document.activeElement).toBe(toggle());
  });

  it("is remembered with the words until they were sent: off at the next opening after Cancel or a send that failed, on again after one that worked", async () => {
    const fetcher = daemonRoutes(zip, () => json({ ok: false, reason: "offline" }));
    make();
    await open();
    await press(toggle());
    await press(button("Cancel"));
    await open();
    expect(row().classList.contains("off")).toBe(true);
    await write("words");
    await press(button("Send"));
    expect(dialog()).toBeNull();
    expect(wrapper.get(".help-result .field-error").text()).toBe("Not sent: no internet connection.");
    await open();
    expect(row().classList.contains("off")).toBe(true);
    expect(area().value).toBe("words");
    fetcher.mockImplementation(() => json({ ok: true, ref: REF }));
    await press(button("Send"));
    expect(fetcher.mock.calls.map((call) => asked(call).body.file)).toEqual([false, false]);
    await open();
    expect(row().classList.contains("off")).toBe(false);
    expect(area().value).toBe("");
  });

  it("sends the downloaded file when it was taken off and put back", async () => {
    const fetcher = daemonRoutes();
    make();
    await open();
    await press(fileName());
    await press(toggle());
    await press(toggle());
    await typeAndSend("x");
    expect(asked(fetcher.mock.calls[1]).body.file).toBe(MADE);
  });
});

describe("nothing in the dialog moves", () => {
  /**
   * The row as it stands in the page: every element with its classes but the ones that only colour
   * it, and the words that take room (both faces of the ×, shown or not).
   */
  const shape = () =>
    [...row().querySelectorAll("*")].map((part) => [
      part.tagName,
      [...part.classList].filter((name) => name !== "twowords-off").join(" "),
      part.children.length === 0 ? part.textContent?.trim() : "",
    ]);

  it("has the same elements and the same words in the file's row with the file and without it, and the same parts round it", async () => {
    make();
    await open();
    const withFile = shape();
    const parts = () => [...(dialog()?.children ?? [])].map((part) => `${part.tagName}.${part.className.replace(/ ?off/, "")}`);
    const round = parts();
    expect(withFile.map((part) => part[2]).filter(Boolean)).toEqual([NAME, "×", "Attach"]);
    await press(toggle());
    expect(shape()).toEqual(withFile);
    expect(parts()).toEqual(round);
    await press(toggle());
    expect(shape()).toEqual(withFile);
  });

  it("holds both faces of the × in one place, the one not shown hidden, and changes only colours on a file that is off", () => {
    expect(cssRule(".twowords")).toMatch(/display:\s*inline-grid/);
    expect(cssRule(".twowords > span")).toMatch(/grid-area:\s*1\s*\/\s*1/);
    expect(cssRule(".twowords > .twowords-off")).toMatch(/visibility:\s*hidden/);
    const sizes =
      /(^|;)\s*(display|width|min-width|height|min-height|padding[a-z-]*|margin[a-z-]*|border(-width|-style)?|font[a-z-]*|line-height|gap|flex[a-z-]*)\s*:/;
    const off = [
      ".logsdialog-attached.off",
      ".logsdialog-attached.off .logsdialog-file",
      ".logsdialog-attached.off .logsdialog-x",
      ".logsdialog-attached.off .logsdialog-x .twowords",
    ];
    for (const selector of off) {
      expect(cssRule(selector), selector).not.toBe("");
      expect(cssRule(selector), selector).not.toMatch(sizes);
    }
    // (Attach is underlined as a link is: the line is on the box of the two faces, where it reaches
    // the word; one on the button would stop at that box)
    expect(cssRule(".logsdialog-attached.off .logsdialog-x .twowords")).toMatch(/text-decoration:\s*underline/);
    expect(cssRule(".logsdialog-attached.off .logsdialog-x")).not.toMatch(/text-decoration/);
    expect(cssRule(".logsdialog-x")).toMatch(/flex:\s*none/);
  });

  it("always has the room for what the download says, a line of its own under the file: two lines, three on a phone, and the dialog has its own width", async () => {
    expect(cssRule(".logsdialog-status")).toMatch(/min-height:\s*2\.8em/);
    expect(cssRule(".logsdialog-status")).toMatch(/line-height:\s*1\.4/);
    // not beside Send and Cancel, where a file's full name takes three lines on a phone
    expect(cssRule(".logsdialog-status")).not.toMatch(/flex/);
    expect(mediaRule("(max-width: 420px)", ".logsdialog-status")).toMatch(/min-height:\s*4\.2em/);
    expect(cssRule(".logsdialog")).toMatch(/width:\s*min\(460px, 100%\)/);
    daemonRoutes();
    make();
    await open();
    const parts = () => [...(dialog()?.children ?? [])].map((part) => `${part.tagName}.${part.className.replace(/ ?off/, "")}`);
    const foot = () => [...(dialog()?.querySelector(".logsdialog-foot")?.children ?? [])].map((part) => `${part.tagName}.${part.className}`);
    const before = parts();
    expect(before.slice(-3)).toEqual(["DIV.logsdialog-attached", "P.logsdialog-status", "FOOTER.logsdialog-foot"]);
    expect(foot()).toEqual(["BUTTON.btn primary", "BUTTON.btn"]);
    await press(fileName());
    expect(statusLine().textContent?.trim()).not.toBe("");
    expect(parts()).toEqual(before);
    await press(toggle());
    expect(parts()).toEqual(before);
    expect(foot()).toEqual(["BUTTON.btn primary", "BUTTON.btn"]);
  });
});

describe("the words of the file's row in nine languages", () => {
  const NEW = ["settings.help.dialog.download", "settings.help.dialog.remove", "settings.help.dialog.attach"] as const;
  const GONE = ["settings.help.dialog.tip_label", "settings.help.dialog.tip", "settings.help.dialog.tip2"];

  it("are nine", () => {
    expect(LOCALES.map((locale) => locale.code).sort()).toEqual(["de", "en", "es", "fi", "fr", "it", "ja", "nl", "pt-BR"]);
  });

  for (const locale of LOCALES) {
    it(`${locale.name}: Download and Remove name the file, Attach is one word of its own, and the sentences of the old (i) are gone`, () => {
      const messages = locale.messages as Record<string, unknown>;
      const [download, remove, attach] = NEW.map((id) => String(messages[id]));
      expect(download).toContain("{file}");
      expect(remove).toContain("{file}");
      // the words of the path builder's ×
      expect(remove).toBe(String(messages["pathbuilder.remove"]).replace("{call}", "{file}"));
      expect(attach).toMatch(/^\S+$/u);
      expect(new Set([download, remove, attach]).size).toBe(3);
      for (const id of GONE) expect(messages[id], id).toBeUndefined();
    });
  }
});
