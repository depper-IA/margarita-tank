import { crab, pick, px, rect, type AnimFn } from './kit'

// clawd-working-typing.svg: arms tap a laptop (we see its back), eyes scan, data bits float up.
export const typing: AnimFn = (g, f) => {
  crab(g, { armL: 1 + (f % 2), armR: 1 + ((f + 1) % 2), eyes: 'squint', eyeDx: pick([-1, 0, 1, 0], f) })
  rect(g, 3, 10, 9, 4, '#78909C')
  rect(g, 2, 14, 11, 1, '#546E7A')
  px(g, 7, 11, f % 2 === 0 ? '#FFFFFF' : '#40C4FF')
  ;[1, 6, 13].forEach((x, k) => {
    const y = 9 - ((f + k * 2) % 5) * 2
    if (y >= 0) px(g, x, y, '#40C4FF')
  })
}
