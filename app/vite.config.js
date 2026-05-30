import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

// GitHub Pages:
// - Project site: https://<user>.github.io/<repo>/  → base `/<repo>/`
// - User/org site: https://<user>.github.io/       → repo name ends with .github.io → base `/`
const repo = process.env.GITHUB_REPOSITORY?.split('/')[1] ?? ''
const githubBase =
  repo.endsWith('.github.io') ? '/' : repo ? `/${repo}/` : '/'
const base =
  process.env.VITE_BASE_PATH ||
  (process.env.GITHUB_PAGES === 'true' ? githubBase : '/')

// Public deploys: pass --demo via run-vite.mjs or set VITE_DEMO_BUILD=1 → synthetic
// JSON + sketches only (safe to git). The LL bundle paths also swap so the overlap
// explorer reads ll_sketches_demo.{bin,json}.
const useDemo = process.env.VITE_DEMO_BUILD === '1'
const phenotypeCountsFile = useDemo
  ? 'phenotype_counts_dp_demo.json'
  : 'phenotype_counts_dp.json'
const llSketchesJsonFile = useDemo ? 'll_sketches_demo.json' : 'll_sketches.json'
const llSketchesBinFile  = useDemo ? 'll_sketches_demo.bin'  : 'll_sketches.bin'

// https://vite.dev/config/
export default defineConfig({
  base,
  define: {
    'import.meta.env.VITE_PHENOTYPE_COUNTS_FILE': JSON.stringify(phenotypeCountsFile),
    'import.meta.env.VITE_LL_SKETCHES_JSON': JSON.stringify(llSketchesJsonFile),
    'import.meta.env.VITE_LL_SKETCHES_BIN':  JSON.stringify(llSketchesBinFile),
  },
  plugins: [svelte()],
})
