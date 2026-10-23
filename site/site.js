// The project page's only script: the copy buttons and the lightbox of the screenshots. Without it the page reads the same: the buttons stay hidden and a screenshot opens as a file.
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

  const box = document.getElementById("lightbox");
  if (!(box instanceof HTMLDialogElement) || typeof box.showModal !== "function") return;
  const image = box.querySelector("img");
  const caption = box.querySelector("p");
  const dark = window.matchMedia("(prefers-color-scheme: dark)");
  const slides = [...document.querySelectorAll(".gallery a.zoom")].map((a) => ({ href: a.getAttribute("href") || "", dark: a.dataset.dark || "", text: a.textContent?.trim() || "" }));
  let index = 0;

  function show(i) {
    index = (i + slides.length) % slides.length;
    const slide = slides[index];
    image.src = dark.matches && slide.dark ? slide.dark : slide.href;
    image.alt = slide.text;
    caption.textContent = `${slide.text} (${index + 1} of ${slides.length})`;
  }

  for (const link of document.querySelectorAll("a.zoom")) {
    link.addEventListener("click", (event) => {
      const found = slides.findIndex((s) => s.href === link.getAttribute("href"));
      if (found < 0 || event.ctrlKey || event.metaKey || event.shiftKey) return;
      event.preventDefault();
      show(found);
      box.showModal();
    });
  }

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
