import { crab, px, rect, type AnimFn } from './kit'

// clawd-idle-living.svg: a 16 s sequence (32 ticks here): glance right, glance left,
// scratch with the left arm, then a big yawn with a stretch and a tear.
export const idleLiving: AnimFn = (g, f) => {
  const c = f % 32
  if (c >= 6 && c <= 9) return crab(g, { dx: 1, eyeDx: 1 })
  if (c >= 14 && c <= 17) return crab(g, { dx: -1, eyeDx: -1 })
  if (c >= 20 && c <= 25) return crab(g, { eyes: 'squint', armL: c % 2 === 0 ? -3 : -2 })
  if (c === 28) return crab(g, { eyes: 'shut', armL: -1, armR: -1 })
  if (c === 29) {
    crab(g, { dy: -1, eyes: 'shut', armL: -3, armR: -3 })
    rect(g, 6, 9, 3, 2, '#000000')
    return
  }
  if (c === 30) {
    crab(g, { dy: -2, eyes: 'shut', armL: -4, armR: -4 })
    rect(g, 6, 8, 3, 3, '#000000')
    px(g, 3, 8, '#40C4FF')
    return
  }
  if (c === 31) {
    crab(g, { dy: 1, eyes: 'shut', armL: 1, armR: 1 })
    px(g, 3, 11, '#40C4FF')
    rect(g, 7, 11, 1, 1, '#000000')
    return
  }
  crab(g, { eyes: c === 4 || c === 12 || c === 19 ? 'shut' : 'open', armL: c === 0 ? 1 : 0 })
}
