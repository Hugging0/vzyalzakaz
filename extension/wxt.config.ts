import { defineConfig } from "wxt";

const marketplaceHosts = [
  "https://freelancer.com/*",
  "https://*.freelancer.com/*",
  "https://freelance.ru/*",
  "https://*.freelance.ru/*",
  "https://fl.ru/*",
  "https://*.fl.ru/*",
  "https://kwork.ru/*",
  "https://*.kwork.ru/*",
];

export default defineConfig({
  modules: ["@wxt-dev/module-react"],
  manifest: {
    name: "ВзялЗаказ",
    short_name: "ВзялЗаказ",
    description: "Подготавливает отклик на площадке и оставляет отправку под вашим контролем.",
    minimum_chrome_version: "120",
    permissions: ["alarms", "storage"],
    host_permissions: ["https://vzyalzakaz.ru/*", ...marketplaceHosts],
    externally_connectable: {
      matches: ["https://vzyalzakaz.ru/*", "http://localhost/*", "http://127.0.0.1/*"],
    },
    icons: {
      16: "icon/16.png",
      32: "icon/32.png",
      48: "icon/48.png",
      128: "icon/128.png",
    },
    action: {
      default_title: "ВзялЗаказ",
      default_icon: {
        16: "icon/16.png",
        32: "icon/32.png",
      },
    },
  },
});
