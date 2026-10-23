import "./style.css";
import "./responsive.css";
import { createApp } from "vue";
import AccessGate from "./AccessGate.vue";
import { listenForInstall } from "./composables/useInstall";
import { registerWorker } from "./lib/worker";

listenForInstall();
registerWorker();
createApp(AccessGate).mount("#app");
