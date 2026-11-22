// What a person reads in an element: its text without the hidden face of a TwoWords. VTU's `text()`
// reads both.
export function shown(wrapper: { element: Element } | undefined): string {
  const copy = wrapper?.element.cloneNode(true) as Element | undefined;
  copy?.querySelectorAll(".twowords-off").forEach((off) => off.remove());
  return (copy?.textContent ?? "").trim();
}

export function seen(wrapper: { element: Element } | undefined): string {
  const copy = wrapper?.element.cloneNode(true) as Element | undefined;
  copy?.querySelectorAll(".sr-only").forEach((hidden) => hidden.remove());
  return (copy?.textContent ?? "").trim();
}
