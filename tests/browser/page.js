// What the browser suite reads in the page: added before the page's own scripts (tests/browser/drive.py).
// Each check returns a list of findings, one string each, naming the element by a short path and its text.
(() => {
  // The map draws on a canvas of its own; MapLibre's controls are not the page's.
  const SKIP = ".maplibregl-map, .maplibregl-canvas-container, .sr-only, [inert], [aria-hidden=true]";
  // MapLibre's constructor sets this._controls: the instance is kept for the checks of the map.
  window.__neoMaps = [];
  Object.defineProperty(Object.prototype, "_controls", {
    configurable: true,
    set(value) {
      Object.defineProperty(this, "_controls", { value, writable: true, configurable: true, enumerable: true });
      if (typeof this.getCanvas === "function") window.__neoMaps.push(this);
    },
  });

  // The page's socket, watched: what came, which topics, and the saves not yet answered. `drop` closes
  // it as a lost connection would (the page then connects again by itself).
  const Native = window.WebSocket;
  const socket = (window.__neoSocket = { opened: 0, received: 0, topics: [], states: 0, asked: [], answered: [], current: null, sentAt: 0, heardAt: 0 });
  window.WebSocket = class extends Native {
    constructor(...args) {
      super(...args);
      socket.current = this;
      this.addEventListener("open", () => socket.opened++);
      this.addEventListener("message", (event) => {
        socket.received++;
        socket.heardAt = performance.now();
        if (typeof event.data !== "string") return;
        try {
          const m = JSON.parse(event.data);
          if (m.type === "state") socket.states++;
          if (m.type === "state" && !socket.topics.includes(m.topic)) socket.topics.push(m.topic);
          if ((m.type === "saved" || m.type === "error") && typeof m.id === "number") socket.answered.push(m.id);
        } catch {
          // (not JSON: the page itself says so)
        }
      });
    }
    send(data) {
      try {
        const c = JSON.parse(data);
        if (c.cmd === "set_config" && typeof c.id === "number") socket.asked.push(c.id);
        if (c.cmd !== "ping") socket.sentAt = performance.now();
      } catch {
        // (as above)
      }
      super.send(data);
    }
  };
  window.__neoSocketDrop = () => socket.current && socket.current.close(4000, "dropped by the browser suite");

  // A hidden tab, simulated: the headless browser has no window to hide, so the page is told it is hidden
  // as the browser would tell it (its timers and frames are not slowed as a real hidden tab's are).
  window.__neoHide = (hidden) => {
    Object.defineProperty(document, "hidden", { configurable: true, get: () => hidden });
    Object.defineProperty(document, "visibilityState", { configurable: true, get: () => (hidden ? "hidden" : "visible") });
    document.dispatchEvent(new Event("visibilitychange"));
  };

  // (an SVG's own parts are drawn inside its box, whatever their own boxes say)
  const shown = (e) =>
    e instanceof Element &&
    !(e instanceof SVGElement && e.ownerSVGElement) &&
    e.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) &&
    !e.closest(SKIP) &&
    (() => {
      const r = e.getBoundingClientRect();
      return r.width >= 1 && r.height >= 1;
    })();

  const ownText = (e) =>
    [...e.childNodes]
      .filter((n) => n.nodeType === Node.TEXT_NODE)
      .map((n) => n.textContent)
      .join("")
      .replace(/\s+/g, " ")
      .trim();

  const name = (e) => {
    const parts = [];
    for (let n = e; n && n !== document.body && parts.length < 4; n = n.parentElement) {
      const cls = typeof n.className === "string" ? n.className.trim().split(/\s+/).filter(Boolean)[0] : "";
      parts.unshift(n.tagName.toLowerCase() + (n.id ? "#" + n.id : "") + (cls ? "." + cls : ""));
      if (n.id) break;
    }
    const text = (ownText(e) || (typeof e.value === "string" ? e.value : "") || (e.firstElementChild ? ownText(e.firstElementChild) : "")).slice(0, 40);
    return parts.join(" > ") + (text ? ` "${text}"` : "");
  };

  const within = (root) => [...(root ? document.querySelectorAll(root) : [document.body])].flatMap((r) => [...r.querySelectorAll("*")]).filter(shown);

  // The nearest ancestor that clips or scrolls sideways what an element shows: only the ancestors from
  // its containing block on do (a fixed element is clipped by none).
  const clipper = (e) => {
    let pos = getComputedStyle(e).position;
    for (let n = e.parentElement; n && n !== document.documentElement; n = n.parentElement) {
      if (pos === "fixed") return null;
      const cs = getComputedStyle(n);
      const holds = cs.position !== "static" || cs.transform !== "none" || cs.contain.includes("paint");
      if (pos === "absolute" && !holds) continue;
      if (cs.overflowX !== "visible") return n;
      if (pos === "absolute" || cs.position !== "static") pos = cs.position;
    }
    return null;
  };

  // Text laid out as written (a log, a terminal): its lines may end in spaces that hang past the box.
  const written = (cs) => cs.whiteSpace.startsWith("pre") || cs.whiteSpace === "break-spaces";

  const box = (n) => {
    const r = n.getBoundingClientRect();
    const left = r.left + n.clientLeft;
    return { left, right: left + n.clientWidth, top: r.top + n.clientTop, bottom: r.top + n.clientTop + n.clientHeight };
  };

  // An element's place under `base`: the index of each step down, with the id where there is one.
  const place = (base, e) => {
    const path = [];
    for (let n = e; n && n !== base; n = n.parentElement) path.unshift([...n.parentElement.children].indexOf(n) + (n.id ? "#" + n.id : ""));
    return path.join("/");
  };

  const canvas = document.createElement("canvas").getContext("2d");
  const textWidth = (text, style) => {
    canvas.font = style.font;
    return canvas.measureText(text).width;
  };

  const SLACK = 1; // px a box may differ by rounding
  const UNANSWERED = 120; // frames a command may go unanswered before the page counts as still

  window.NeoChecks = {
    // Boxes past the viewport or past the clipping box they sit in.
    outside(root, allowed) {
      const found = [];
      const W = document.documentElement.clientWidth;
      for (const e of within(root)) {
        if (allowed && e.closest(allowed)) continue;
        const r = e.getBoundingClientRect();
        if (getComputedStyle(e).position !== "fixed" && (r.right > W + SLACK || r.left < -SLACK)) {
          found.push(`${name(e)} is past the screen: ${Math.round(r.left)}..${Math.round(r.right)} of ${W}`);
          continue;
        }
        const c = clipper(e);
        if (!c || c === document.body || (allowed && c.closest(allowed))) continue;
        const b = box(c);
        if (r.right > b.right + SLACK || r.left < b.left - SLACK)
          found.push(`${name(e)} is past ${name(c)}: ${Math.round(r.left)}..${Math.round(r.right)} in ${Math.round(b.left)}..${Math.round(b.right)}`);
      }
      return found;
    },

    // Text wider or higher than the box that shows it, or drawn outside it.
    clipped(root, allowed) {
      const found = [];
      for (const e of within(root)) {
        const text = ownText(e);
        if (!text || (allowed && e.closest(allowed))) continue;
        if (["INPUT", "TEXTAREA", "SELECT", "OPTION"].includes(e.tagName)) continue;
        const cs = getComputedStyle(e);
        if (cs.overflowX !== "visible" && e.scrollWidth > e.clientWidth + SLACK && e.clientWidth > 0)
          found.push(`${name(e)} cuts its text: ${e.scrollWidth} > ${e.clientWidth} px`);
        else if (cs.overflowY !== "visible" && e.scrollHeight > e.clientHeight + 2 && e.clientHeight > 0 && cs.overflowY !== "auto" && cs.overflowY !== "scroll")
          found.push(`${name(e)} cuts its text below: ${e.scrollHeight} > ${e.clientHeight} px`);
        else if (!["auto", "scroll"].includes(cs.overflowX) && !written(cs)) {
          const r = e.getBoundingClientRect();
          for (const node of e.childNodes) {
            if (node.nodeType !== Node.TEXT_NODE || !node.textContent.trim()) continue;
            const range = document.createRange();
            range.selectNodeContents(node);
            const t = range.getBoundingClientRect();
            if (t.width && (t.right > r.right + SLACK || t.left < r.left - SLACK)) {
              found.push(`${name(e)} draws its text outside its box: ${Math.round(t.left)}..${Math.round(t.right)} in ${Math.round(r.left)}..${Math.round(r.right)}`);
              break;
            }
          }
        }
      }
      return found;
    },

    // A select narrower than the words of an entry it may show; an allowed one is held to the entry it
    // shows only.
    selects(root, arrow, allowed, cut) {
      const found = [];
      for (const e of within(root)) {
        if (e.tagName !== "SELECT" || (cut && e.matches(cut))) continue;
        const cs = getComputedStyle(e);
        const room = e.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight) - arrow;
        const entries = allowed && e.matches(allowed) ? [e.options[e.selectedIndex]].filter(Boolean) : [...e.options];
        for (const o of entries) {
          if (!o.text.trim()) continue;
          const w = textWidth(o.text, cs);
          if (w > room + SLACK) {
            found.push(`${name(e)} is too narrow for "${o.text}": ${Math.round(w)} px of words in ${Math.round(room)}`);
            break;
          }
        }
      }
      return found;
    },

    // The room a select's arrow takes: an auto-width select is its widest entry, its padding and the arrow.
    arrow() {
      const s = document.createElement("select");
      s.className = "input";
      s.style.width = "auto";
      const o = document.createElement("option");
      o.text = "Some words of an entry";
      s.append(o);
      document.body.append(s);
      const cs = getComputedStyle(s);
      const room = s.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight) - textWidth(o.text, cs);
      s.remove();
      return room;
    },

    // Siblings in the flow whose boxes cross.
    overlaps(root, allowed) {
      const found = [];
      const seen = new Set();
      for (const e of within(root)) {
        const parent = e.parentElement;
        if (!parent || seen.has(parent)) continue;
        seen.add(parent);
        const kids = [...parent.children].filter(
          (k) => shown(k) && ["static", "relative", "sticky"].includes(getComputedStyle(k).position) && getComputedStyle(k).display !== "inline" && !(allowed && k.closest(allowed)),
        );
        for (let i = 0; i < kids.length; i++) {
          const a = kids[i].getBoundingClientRect();
          for (let j = i + 1; j < kids.length; j++) {
            const b = kids[j].getBoundingClientRect();
            const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
            const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
            if (w > 2 && h > 2) found.push(`${name(kids[i])} and ${name(kids[j])} lie over each other: ${Math.round(w)} x ${Math.round(h)} px`);
          }
        }
      }
      return found;
    },

    // Text with no room at a side of the box it stands in: the nearest ancestor that shows its edge (a
    // border, a ground of its own) or that scrolls (a pane).
    edges(root, gap, allowed) {
      const found = [];
      const seen = (n) => {
        const cs = getComputedStyle(n);
        const ground = cs.backgroundColor !== "rgba(0, 0, 0, 0)" && cs.backgroundColor !== "transparent";
        return parseFloat(cs.borderLeftWidth) > 0 || parseFloat(cs.borderRightWidth) > 0 || ground || ["auto", "scroll"].includes(cs.overflowY);
      };
      for (const e of within(root)) {
        if (!ownText(e) || (allowed && e.closest(allowed)) || written(getComputedStyle(e))) continue;
        let b = e;
        while (b && b !== document.body && !seen(b)) b = b.parentElement;
        if (!b || b === document.body) continue;
        const cs = getComputedStyle(b);
        const r = b.getBoundingClientRect();
        const left = r.left + parseFloat(cs.borderLeftWidth);
        const right = r.right - parseFloat(cs.borderRightWidth);
        for (const node of e.childNodes) {
          if (node.nodeType !== Node.TEXT_NODE || !node.textContent.trim()) continue;
          const range = document.createRange();
          range.selectNodeContents(node);
          const t = [...range.getClientRects()].filter((x) => x.width > 0);
          if (t.some((x) => x.left - left < gap || right - x.right < gap)) {
            const l = Math.min(...t.map((x) => x.left));
            const rr = Math.max(...t.map((x) => x.right));
            found.push(`${name(e)} has no room at the side of ${name(b)}: text ${Math.round(l)}..${Math.round(rr)} in ${Math.round(left)}..${Math.round(right)}`);
            break;
          }
        }
      }
      return found;
    },

    // Every shown element's box by its place in the tree, for "nothing moves".
    boxes(root, skip) {
      const out = {};
      const base = document.querySelector(root);
      if (!base) return out;
      let i = 0;
      for (const e of base.querySelectorAll("*")) {
        i++;
        if (!shown(e) || (skip && e.closest(skip))) continue;
        const r = e.getBoundingClientRect();
        // (its own words in the key: an element whose words change is another one, not one that moved)
        const path = place(base, e);
        const field = e.closest(".field")?.querySelector("label, .field-label")?.textContent ?? "";
        out[[path, e.tagName, ownText(e), e.parentElement ? ownText(e.parentElement) : "", field].join(" / ")] = { path, order: i, name: name(e), r: [r.left, r.top + base.scrollTop, r.width, r.height].map((x) => Math.round(x * 10) / 10) };
      }
      return out;
    },

    // The places of everything shown under `root`, as one text: equal when nothing moved.
    signature(root, skip) {
      return JSON.stringify(Object.values(window.NeoChecks.boxes(root, skip)).map((b) => b.r));
    },

    place(root, e) {
      return place(document.querySelector(root), e);
    },

    // Resolves once every save is answered and the boxes under `root` have kept still for `frames` frames.
    quiet(root, frames, skip) {
      const base = document.querySelector(root);
      const signature = () =>
        base
          ? [...base.querySelectorAll("*")]
              .filter((e) => shown(e) && !(skip && e.closest(skip)))
              .map((e) => {
                const r = e.getBoundingClientRect();
                return `${Math.round(r.left)},${Math.round(r.top + base.scrollTop)},${Math.round(r.width)},${Math.round(r.height)}`;
              })
              .join(";")
          : "";
      // a save not answered yet, or a command the daemon has said nothing since (for at most UNANSWERED frames:
      // a command that is not answered at all must not hold the wait)
      let waited = 0;
      const pending = () =>
        socket.asked.some((id) => !socket.answered.includes(id)) || (socket.sentAt > socket.heardAt && ++waited < UNANSWERED);
      return new Promise((resolve) => {
        let last = "";
        let still = 0;
        const step = () => {
          const now = signature();
          still = now === last && !pending() ? still + 1 : 0;
          last = now;
          if (still >= frames) resolve(true);
          else requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
      });
    },

    // House rules that the tree shows: an (i) has its name in aria-label and no title.
    infos() {
      return [...document.querySelectorAll(".info-toggle")]
        .filter((b) => !b.getAttribute("aria-label") || b.hasAttribute("title"))
        .map((b) => `${name(b)}: aria-label ${JSON.stringify(b.getAttribute("aria-label"))}, title ${JSON.stringify(b.getAttribute("title"))}`);
    },

    // A table in a card that stands out of the column of the card's text (its fields' words).
    columns() {
      const found = [];
      const left = (root) =>
        Math.min(
          ...[...root.querySelectorAll("*")]
            .filter((e) => ownText(e) && shown(e))
            .map((e) => {
              const range = document.createRange();
              range.selectNodeContents(e);
              return range.getBoundingClientRect().left;
            }),
        );
      for (const card of document.querySelectorAll(".card")) {
        const fields = card.querySelector(".card-fields");
        if (!shown(card) || !fields) continue;
        const column = left(fields);
        for (const table of card.querySelectorAll("table"))
          if (shown(table) && left(table) < column - SLACK) found.push(`${name(table)} stands ${Math.round(column - left(table))} px left of the words of ${name(card)}`);
      }
      return found;
    },

    // Two elements with one id: a label then names the wrong control.
    sameIds() {
      const count = {};
      for (const e of document.querySelectorAll("[id]")) count[e.id] = (count[e.id] || 0) + 1;
      return Object.entries(count)
        .filter(([, n]) => n > 1)
        .map(([id, n]) => `${n} elements have the id ${id}: ${[...document.querySelectorAll(`[id="${CSS.escape(id)}"]`)].map(name).join(", ")}`);
    },

    // The words shown on the page, each with the element that shows them.
    texts(root, skip) {
      const out = [];
      for (const e of within(root)) {
        if (skip && e.closest(skip)) continue;
        const text = ownText(e);
        if (text) out.push([name(e), text]);
        for (const a of ["aria-label", "title", "placeholder"]) {
          const v = e.getAttribute(a);
          if (v && v.trim()) out.push([`${name(e)} [${a}]`, v.trim()]);
        }
      }
      return out;
    },
  };
})();
