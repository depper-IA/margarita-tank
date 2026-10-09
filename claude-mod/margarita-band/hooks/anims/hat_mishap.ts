import { crab, pick, px, type AnimFn } from './kit'
import { hat } from './wizard'

// clawd-hat-mishap.svg (a WebSearch/WebFetch call failed): the wizard hat slips over the eyes.
export const hatMishap: AnimFn = (g, f) => {
  const p = f % 6
  const oy = pick([0, 0, 1, 4, 4, 2], p)
  const ox = pick([0, 0, 1, 0, -1, 0], p)
  crab(g, { armR: p >= 4 ? -2 : 0, eyes: 'open' })
  hat(g, ox, oy, '#5865C8', '#2C2557')
  if (p % 2 === 1) px(g, 14, 3, '#FFF3A8')
  if (p % 3 === 0) px(g, 1, 4, '#DCC5FF')
}
