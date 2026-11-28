// A list a reader scrolled up in keeps what he looks at where it is when rows come or go above it:
// the first row in view is found before the change and the list is scrolled so that it stands where
// it stood. Chromium's scroll anchoring would do it too; WebKit has none.

/** Measure the list now; the function returned, called after the change, puts the row back. */
export function keepPlace(box: HTMLElement | null): () => void {
  if (box === null) return () => undefined;
  const top = box.getBoundingClientRect().top;
  const anchor = [...box.children].find((row) => row.getBoundingClientRect().bottom > top);
  if (anchor === undefined) return () => undefined;
  const stood = anchor.getBoundingClientRect().top - top;
  return () => {
    if (anchor.isConnected)
      box.scrollTop += anchor.getBoundingClientRect().top - box.getBoundingClientRect().top - stood;
  };
}
