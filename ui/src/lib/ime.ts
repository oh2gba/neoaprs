// The Enter of a text field that confirms it. The Enter that ends an IME composition (a Japanese
// conversion, say) is the composition's own and confirms nothing: engines mark it by `isComposing`,
// or by the key code 229 for the keydown that comes just after the composition ended.

/** Whether the keydown of an Enter handler (`@keydown.enter`) commits the field. */
export function confirms(event: KeyboardEvent): boolean {
  return !event.isComposing && event.keyCode !== 229;
}
