import { defineConfig, loadEnv } from 'vite'
import react, { reactCompilerPreset } from '@vitejs/plugin-react'
import tsconfigPaths from 'vite-tsconfig-paths'
import babel from '@rolldown/plugin-babel'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd())
  return {
    plugins: [
      react(),
      babel({
        presets: [reactCompilerPreset()],
      }),
      tsconfigPaths(),
    ],
    build: {
      sourcemap: env.VITE_BUILD_SOURCEMAP === 'true',
    },
    server: {
      port: parseInt(env.VITE_PORT) || 3000,
      host: env.VITE_HOST ?? 'localhost',
      allowedHosts: ['.nip.io'],
      // In a local dev setup, we proxy the media server ourselves to avoid CORS issues
      proxy: {
        '/media': {
          target: 'http://localhost:8083',
          changeOrigin: true,
          secure: false,
        },
      },
    },
  }
})
