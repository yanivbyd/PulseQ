import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./global.css";
import App from "./App";

if (window.location.hostname === "localhost") {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" fill="none">
  <rect width="32" height="32" rx="6" fill="#0f172a"/>
  <polyline points="2,16 8,16 11,8 14,24 17,12 20,20 23,16 30,16" stroke="#22c55e" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
</svg>`;
  const link = document.querySelector<HTMLLinkElement>("link[rel~='icon']") ?? document.createElement("link");
  link.rel = "icon";
  link.type = "image/svg+xml";
  link.href = `data:image/svg+xml,${encodeURIComponent(svg)}`;
  document.head.appendChild(link);
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
