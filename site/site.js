// The project page's only script: the copy buttons, the lightbox of the screenshots, and one line to say the page was opened. Without it the page reads the same: the buttons stay hidden and a screenshot opens as a file.
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
