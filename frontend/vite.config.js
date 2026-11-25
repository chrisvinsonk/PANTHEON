import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    host: "127.0.0.1",
    port: Number(process.env.PORT) || 5174,
    strictPort: true,
    proxy: {
      "/api": process.env.VITE_API_BASE_URL || "http://127.0.0.1:8000",
    },
    historyApiFallback: true,
  },
  preview: {
    host: "0.0.0.0",
    port: Number(process.env.PORT) || 5174,
    strictPort: true,
    allowedHosts: ["company-os-re-fe.onrender.com"],
  },
});
