import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
  // Port 8000 is often already taken, so the backend defaults to 8001.
  // Override with VITE_API_TARGET in frontend/.env.local if you move it.
  const env = loadEnv(mode, ".", "");
  const target = env.VITE_API_TARGET || "http://localhost:8001";

  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      // Proxying /api means the browser only ever talks to one origin,
      // so there is no CORS to think about in development.
      proxy: { "/api": { target, changeOrigin: true } },
    },
  };
});
