// Dumps what the mod's real half-block renderer draws for every source frame of each v2
// animation, as JSON on stdout. Consumed by tools/render_mod_preview.py.
//   deno run --allow-read --unstable-sloppy-imports tools/mod_preview_dump.ts
import { ANIMS_V2 } from '../claude-mod/margarita-band/hooks/anims-v2/index.ts'
import { totalHolds } from '../claude-mod/margarita-band/hooks/anims-v2/decode.ts'
import { crabRows } from '../claude-mod/margarita-band/hooks/playback.ts'

const out: Record<string, unknown> = {}
for (const [name, a] of Object.entries(ANIMS_V2)) {
  if (name === 'idle_living' || !a) continue
  const frames = []
  for (let k = 0; k < totalHolds(a); k += 1) {
    // the middle of source frame k, previewed (looping)
    frames.push(crabRows(name as never, 'v2', 0, ((k + 0.5) * 1000) / a.fps, true).rows)
  }
  out[name] = { width: a.width, height: a.height, frames }
}
console.log(JSON.stringify(out))
