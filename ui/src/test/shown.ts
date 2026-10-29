// What a person reads in an element: the text of it without the face of a TwoWords that is hidden (the word of an ask-twice button that is not the one shown). VTU's `text()` reads both.
export function shown(wrapper: { element: Element } | undefined): string {
  const copy = wrapper?.element.cloneNode(true) as Element | undefined;
  copy?.querySelectorAll(".twowords-off").forEach((off) => off.remove());
  return (copy?.textContent ?? "").trim();
}
