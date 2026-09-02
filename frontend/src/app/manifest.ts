import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "ВзялЗаказ",
    short_name: "ВзялЗаказ",
    description: "Персональный агент для поиска и подготовки откликов",
    id: "/app",
    start_url: "/app/today",
    scope: "/",
    display: "standalone",
    background_color: "#F6F3EC",
    theme_color: "#F6F3EC",
    lang: "ru",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
