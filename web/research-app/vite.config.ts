import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  root: new URL(".", import.meta.url).pathname,
  base: "/research/",
  plugins: [react()],
  build: {
    outDir: "../research-dist/research",
    emptyOutDir: true,
    sourcemap: false,
    target: "es2022",
  },
});
