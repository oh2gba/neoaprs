// The addressees of the Email tab used before (addresses and the names of shortcuts), the newest first, remembered in the browser (lib/storage.ts).
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

  /** Puts the addressee first in the list. */
  const remember = (to: string): void => keep(rememberAddress(addresses.value, to));
  /** Takes the addressee out of the list. */
  const forget = (name: string): void => keep(forgetAddress(addresses.value, name));

  return { addresses, remember, forget };
}
