// The project page's only script: the copy buttons, the Download chooser's first choice, the lightbox of the screenshots, the board of HF tests (who is on the air and when), and one line to say the page was opened. Without it the page reads the same: the buttons stay hidden and a screenshot opens as a file.
(() => {
  "use strict";

  for (const button of document.querySelectorAll("button.copy")) {
    button.hidden = false;
    button.addEventListener("click", async () => {
      const text = button.dataset.text || "";
      try {
        await navigator.clipboard.writeText(text);
      } catch {
        const area = document.createElement("textarea");
        area.value = text;
        area.setAttribute("readonly", "");
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.append(area);
        area.select();
        try {
          document.execCommand("copy");
        } catch {
          // nothing to copy with: the line is on screen to select
        }
        area.remove();
      }
      button.textContent = "Copied";
      button.dataset.done = "";
      setTimeout(() => {
        button.textContent = "Copy";
        delete button.dataset.done;
      }, 1800);
    });
  }

  // The Download chooser starts on the reader's own system (Windows without the script): a Raspberry Pi's browser says Linux on ARM. A phone or tablet keeps the default.
  {
    const ua = navigator.userAgent;
    const platform = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "";
    let os = "";
    if (/Android|iPhone|iPad/i.test(ua)) os = "";
    else if (/Win/i.test(platform)) os = "os-win";
    else if (/Mac/i.test(platform)) os = "os-mac";
    else if (/Linux/i.test(platform)) os = /aarch64|arm/i.test(platform + " " + ua) ? "os-pi" : "os-linux";
    const radio = os && document.getElementById(os);
    if (radio instanceof HTMLInputElement) radio.checked = true;
  }

  // A view: the page says it rendered, once, to its own host, after load. Only on the site itself (the mirror on GitHub Pages has no endpoint); nothing is kept in the browser and no cookie is set (what is recorded: the
  // line in the footer).
  if (location.hostname === "neo.oh2gba.eu" && navigator.sendBeacon) {
    addEventListener("load", () => {
      setTimeout(() => {
        try {
          const nav = performance.getEntriesByType("navigation")[0];
          const body = { path: location.pathname, ref: document.referrer || null, w: innerWidth, load: nav && nav.duration > 0 ? Math.round(nav.duration) : null, tz: -new Date().getTimezoneOffset() };
          const who = new URLSearchParams(location.search).get("who");
          if (who !== null) {
            body.who = who.toLowerCase().replace(/[^a-z0-9]/g, "").slice(0, 3) || null;
            const url = new URL(location.href);
            url.searchParams.delete("who");
            history.replaceState(null, "", url.pathname + url.search + url.hash);
          }
          navigator.sendBeacon("/api/v1/view", new Blob([JSON.stringify(body)], { type: "application/json" }));
        } catch {
          // a view that is not counted is no loss to the reader
        }
      }, 0);
    });
  }

  // The suggested HF frequencies, from the same file NeoAPRS itself reads (frequencies.json beside this page): the page's own copy stands when the file cannot be read.
  const dial = document.getElementById("frequencies");
  if (dial && window.fetch) {
    fetch("frequencies.json", { cache: "no-cache" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        const good = (data && Array.isArray(data.frequencies) ? data.frequencies : [])
          .filter((f) => f && /^\d{1,3} m$/.test(f.band) && /^\d{1,2}\.\d{3,4} MHz (USB|LSB)$/.test(f.dial))
          .slice(0, 5)
          .sort((a, b) => parseInt(b.band, 10) - parseInt(a.band, 10));
        const body = dial.querySelector("tbody");
        if (!good.length || !body) return;
        // padded with no-break spaces in the mono font, so that the bands end and the decimal points stand one under another
        const pad = (text, left, right) => " ".repeat(Math.max(0, left)) + text + " ".repeat(Math.max(0, right));
        const aligned = (text) => {
          const [mhz, rest] = text.split(" MHz ");
          const [whole, frac] = mhz.split(".");
          return pad(`${whole}.${frac}`, 2 - whole.length, 4 - frac.length) + " MHz " + rest;
        };
        body.replaceChildren(...good.map((f) => {
          const row = document.createElement("tr");
          const band = document.createElement("th");
          band.scope = "row";
          band.textContent = pad(f.band, 4 - f.band.length, 0);
          const freq = document.createElement("td");
          freq.textContent = aligned(f.dial);
          row.append(band, freq);
          return row;
        }));
      })
      .catch(() => {});
  }

  // The sked board under the HF band: the stations that said when they will be on the air, from the file the board of NeoAPRS writes (skeds.json beside this page), and under it the past tests (skeds-past.json, and the board's own that have ended since it was written),
  // newest first, as NeoAPRS lists them: the 20 newest by their end, kept 30 days. Each of the page's own tables has one row that says there is none, and it stays when nothing was read; else the rows are: the calls, the time (now, for one that has begun) and the dial of each,
  // never the note (free text from strangers does not go on this page). Every value is checked again here and written as text, never as HTML; skeds with the same times and dial are one row.
  const board = document.getElementById("sked-board");
  const pastBoard = document.getElementById("sked-past");
  if (board && window.fetch) {
    const read = (name) =>
      fetch(name, { cache: "no-cache" })
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null);
    Promise.all([read("skeds.json"), read("skeds-past.json")]).then(([data, gone]) => {
      const instant = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;
      const now = Date.now();
      const oldest = now - 30 * 86400000;
      const valid = (list) =>
        (Array.isArray(list) ? list : []).filter(
          (s) =>
            s &&
            typeof s.id === "string" && /^[0-9a-f]{12}$/.test(s.id) &&
            typeof s.call === "string" && /^[A-Z0-9]{3,6}(-\d{1,2})?$/.test(s.call) &&
            typeof s.from === "string" && instant.test(s.from) &&
            typeof s.to === "string" && instant.test(s.to) &&
            Date.parse(s.to) > Date.parse(s.from) && Date.parse(s.to) - Date.parse(s.from) <= 86400000 &&
            typeof s.dial === "string" && /^\d{1,2}\.\d{3,4} MHz (USB|LSB)$/.test(s.dial),
        );
      const listed = valid(data && data.v === 1 ? data.skeds : []);
      const ended = new Map();
      for (const s of [...valid(gone && gone.v === 1 ? gone.past : []), ...listed.filter((s) => Date.parse(s.to) <= now)])
        if (!ended.has(s.id) && Date.parse(s.to) > oldest) ended.set(s.id, s);
      const tests = (skeds) => {
        const rows = new Map();
        for (const s of skeds) {
          const key = `${s.from}|${s.to}|${s.dial}`;
          if (!rows.has(key)) rows.set(key, { from: s.from, to: s.to, dial: s.dial, calls: [] });
          const row = rows.get(key);
          if (!row.calls.includes(s.call)) row.calls.push(s.call);
        }
        return [...rows.values()];
      };
      const coming = tests(
        listed
          .filter((s) => Date.parse(s.to) > now && !ended.has(s.id))
          .sort((a, b) => Date.parse(a.from) - Date.parse(b.from) || Date.parse(a.to) - Date.parse(b.to)),
      ).slice(0, 12);
      const past = tests([...ended.values()].sort((a, b) => (a.id < b.id ? -1 : 1)))
        .sort((a, b) => Date.parse(b.to) - Date.parse(a.to) || Date.parse(b.from) - Date.parse(a.from) || (a.dial < b.dial ? -1 : a.dial > b.dial ? 1 : 0))
        .slice(0, 20);
      const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
      const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
      const two = (n) => String(n).padStart(2, "0");
      const day = (d) => `${days[d.getUTCDay()]} ${d.getUTCDate()} ${months[d.getUTCMonth()]}`;
      const clock = (d) => `${two(d.getUTCHours())}:${two(d.getUTCMinutes())}`;
      const fill = (table, shown) => {
        const body = table && table.querySelector("tbody");
        if (!shown.length || !body) return;
        body.replaceChildren(...shown.map((row) => {
          const start = new Date(row.from);
          const end = new Date(row.to);
          const tr = document.createElement("tr");
          const call = document.createElement("th");
          call.scope = "row";
          call.textContent = row.calls.join(", ");
          const when = document.createElement("td");
          const running = start.getTime() <= now && end.getTime() > now; // a test that has begun is on the air now: the row says so in place of its start
          const until = ` to ${day(running ? new Date(now) : start) === day(end) ? "" : day(end) + " "}${clock(end)}`;
          if (running) {
            const mark = document.createElement("strong");
            mark.textContent = "now";
            when.append(mark, until);
          } else when.textContent = `${day(start)} ${clock(start)}${until}`;
          const dial = document.createElement("td");
          dial.className = "dial";
          dial.textContent = row.dial;
          tr.append(call, when, dial);
          return tr;
        }));
      };
      fill(board, coming);
      fill(pastBoard, past);
    });
  }

  const box = document.getElementById("lightbox");
  if (!(box instanceof HTMLDialogElement) || typeof box.showModal !== "function") return;
  const image = box.querySelector("img");
  const caption = box.querySelector("p");
  const dark = window.matchMedia("(prefers-color-scheme: dark)");
  const slides = [...document.querySelectorAll("a.zoom")].map((a) => ({
    href: a.getAttribute("href") || "",
    dark: a.dataset.dark || "",
    text: a.querySelector("span")?.textContent?.trim() || a.querySelector("img")?.alt || "",
  }));
  let index = 0;

  function show(i) {
    index = (i + slides.length) % slides.length;
    const slide = slides[index];
    image.src = dark.matches && slide.dark ? slide.dark : slide.href;
    image.alt = slide.text;
    caption.textContent = `${slide.text} (${index + 1} of ${slides.length})`;
  }

  document.querySelectorAll("a.zoom").forEach((link, i) => {
    link.addEventListener("click", (event) => {
      if (event.ctrlKey || event.metaKey || event.shiftKey) return;
      event.preventDefault();
      show(i);
      box.showModal();
    });
  });

  box.querySelector(".close").addEventListener("click", () => box.close());
  box.querySelector(".prev").addEventListener("click", () => show(index - 1));
  box.querySelector(".next").addEventListener("click", () => show(index + 1));
  box.addEventListener("click", (event) => {
    if (event.target === box || event.target.classList.contains("lb")) box.close();
  });
  box.addEventListener("keydown", (event) => {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      show(index - 1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      show(index + 1);
    }
  });
})();
