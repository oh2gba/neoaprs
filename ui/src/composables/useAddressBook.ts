// The addressees the Email tab used, newest first, kept in the browser.
import { shallowRef } from "vue";
import { forgetAddress, parseAddresses, rememberAddress } from "@/lib/email";
import { readStored, writeStored } from "@/lib/storage";

const KEY = "emailto";

export function useAddressBook() {
  const addresses = shallowRef<readonly string[]>(parseAddresses(readStored(KEY)));

  function keep(list: readonly string[]): void {
    addresses.value = list;
    writeStored(KEY, JSON.stringify(list));
  }

  const now = (): string[] => parseAddresses(readStored(KEY));
  const remember = (to: string): void => keep(rememberAddress(now(), to));
  const forget = (name: string): void => keep(forgetAddress(now(), name));

  return { addresses, remember, forget };
}
