/// <reference types="vite/client" />
/** The version of NeoAPRS this page is built with (vite.config.ts). */
declare const __PAGE_VERSION__: string;
declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<object, object, unknown>;
  export default component;
}
