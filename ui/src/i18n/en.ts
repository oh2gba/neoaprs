// The English catalogue, the source of every other: an id and its message, in the files of ./en/ by area. The type `MessageId` (catalogue.ts) is made from it, so a catalogue of another language has the same ids or does
// not compile, and `t("id")` with an id that is not here does not either. A new area is a file in ./en/ and a line here.
import { bulletins } from "@/i18n/en/bulletins";
import { email } from "@/i18n/en/email";
import { errors } from "@/i18n/en/errors";
import { messages } from "@/i18n/en/messages";
import { objects } from "@/i18n/en/objects";
import { shell } from "@/i18n/en/shell";
import { time } from "@/i18n/en/time";
import type { Message } from "@/i18n/message";

export const en = { ...shell, ...time, ...errors, ...messages, ...email, ...bulletins, ...objects } as const satisfies Record<string, Message>;
