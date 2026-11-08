import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // The browser only talks to Vite, which forwards API calls to FastAPI.
    // This avoids CORS and keeps the API key on the backend.
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
