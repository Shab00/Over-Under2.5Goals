import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/football-react/',
  build: { outDir: '../football-react', emptyOutDir: true }
})
