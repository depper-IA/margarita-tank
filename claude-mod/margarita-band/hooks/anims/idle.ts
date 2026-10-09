import { crab, pick, type AnimFn } from './kit'

// clawd-static-base.svg: standing crab that breathes (arms sink and rise) and blinks now and then.
export const idle: AnimFn = (g, f) => {
  const exhale = (f >> 1) % 2
  crab(g, { armL: exhale, armR: exhale, eyes: pick(['open', 'open', 'open', 'open', 'open', 'open', 'open', 'open', 'shut'] as const, f) })
}
