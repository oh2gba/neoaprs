/// <reference types="vite/client" />
declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<object, object, unknown>;
  export default component;
}
/** Whether the page is built with encrypted messages: a constant of the build (vite.config.ts). */
declare const __ENCRYPTION__: boolean;
