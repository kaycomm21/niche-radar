import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// GitHub Pages 프로젝트 사이트: https://kaycomm21.github.io/niche-radar/
export default defineConfig({
  plugins: [react()],
  base: process.env.VITE_BASE ?? "./",
});
