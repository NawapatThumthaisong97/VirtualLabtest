import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // listen on 0.0.0.0 so it's reachable from outside the container
    port: 5173,
    watch: { usePolling: true }, // source is bind-mounted from the host - native fs events don't cross into Docker
    proxy: {
      "/api": { target: "http://server:8080", changeOrigin: true },
      "/stream": { target: "http://server:8080", changeOrigin: true },
    },
  },
});
