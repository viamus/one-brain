import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/web/assets/",
  plugins: [react()],
  build: {
    assetsDir: "",
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          mui: ["@mui/material", "@mui/icons-material"],
          emotion: ["@emotion/react", "@emotion/styled"]
        }
      }
    }
  },
  server: {
    port: 5173,
    proxy: {
      "/graph": "http://127.0.0.1:8089",
      "/api": "http://127.0.0.1:8089"
    }
  }
});
