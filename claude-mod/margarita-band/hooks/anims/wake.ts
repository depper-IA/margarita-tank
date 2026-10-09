import { crab, type AnimFn } from './kit'
import { sploot } from './sleeping'

// clawd-wake.svg (one shot): legs grow, torso rises from the sploot, a stretch, eyes open.
export const wake: AnimFn = (g, f) => {
  if (f <= 0) return sploot(g, 0, true)
  if (f === 1) return crab(g, { dy: 2, eyes: 'squint', armL: 1, armR: 1 })
  if (f === 2) return crab(g, { dy: 1, eyes: 'squint' })
  if (f === 3) return crab(g, { dy: -1, eyes: 'shut', armL: -3, armR: -3 })
  crab(g, {})
}
