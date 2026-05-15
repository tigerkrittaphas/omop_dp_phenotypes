/**
 * Forwards to the Vite CLI but accepts --demo (stripped before spawn).
 * Sets VITE_DEMO_BUILD=1 so vite.config.js bundles phenotype_counts_dp_demo.json.
 */
import { spawn } from 'node:child_process'

const argv = process.argv.slice(2)
const demo = argv.includes('--demo')
const viteArgv = argv.filter((a) => a !== '--demo')
if (demo) process.env.VITE_DEMO_BUILD = '1'

const child = spawn('vite', viteArgv, {
  stdio: 'inherit',
  env: process.env,
  shell: process.platform === 'win32',
})

child.on('exit', (code, signal) => {
  if (signal) process.kill(process.pid, signal)
  process.exit(code ?? 0)
})
