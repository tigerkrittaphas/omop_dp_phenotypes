import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

// GitHub project pages: https://<user>.github.io/<repo>/
const repo = process.env.GITHUB_REPOSITORY?.split('/')[1] ?? ''
const base =
  process.env.VITE_BASE_PATH ||
  (process.env.GITHUB_PAGES === 'true' && repo ? `/${repo}/` : '/')

// Public deploys: pass --demo via run-vite.mjs or set VITE_DEMO_BUILD=1 → synthetic JSON only (safe to git).
const useDemo = process.env.VITE_DEMO_BUILD === '1'
const phenotypeCountsFile = useDemo
  ? 'phenotype_counts_dp_demo.json'
  : 'phenotype_counts_dp.json'

// https://vite.dev/config/
export default defineConfig({
  base,
  define: {
    'import.meta.env.VITE_PHENOTYPE_COUNTS_FILE': JSON.stringify(phenotypeCountsFile),
  },
  plugins: [svelte()],
})
