import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // The repo has one root .env (files/coding-standards.md section 10's
  // convention, already how backend/src/config.py resolves its env file)
  // rather than a separate frontend/.env -- point Vite's own env loading
  // at it so `npm run dev` picks up VITE_API_BASE_URL without a second
  // file to keep in sync.
  envDir: "..",
});
