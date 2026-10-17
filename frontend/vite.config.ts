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
  server: {
    watch: {
      // Docker Desktop on Windows doesn't forward inotify events for a
      // bind-mounted host directory (docker-compose.override.yml mounts
      // ./frontend/src into the container), so chokidar's native watcher
      // never fires and HMR silently stops picking up edits -- confirmed
      // by editing a component and seeing no [vite] HMR log line at all
      // until the container was restarted. CHOKIDAR_USEPOLLING is set by
      // docker-compose.override.yml's frontend service only; `make
      // dev-frontend`'s non-Docker path leaves it unset and keeps the
      // cheaper native watcher.
      usePolling: process.env.CHOKIDAR_USEPOLLING === "true",
    },
  },
});
