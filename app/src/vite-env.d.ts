/// <reference types="svelte" />
/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Set at build time: phenotype_counts_dp_demo.json (demo) or phenotype_counts_dp.json (local real). */
  readonly VITE_PHENOTYPE_COUNTS_FILE: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
