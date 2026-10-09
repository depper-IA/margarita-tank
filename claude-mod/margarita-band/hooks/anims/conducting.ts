import { crab, pick, px, type AnimFn } from './kit'

// clawd-working-conducting.svg: calm bobbing, arms swoop out of phase, a stream of colored
// pixels arcs over the head from one hand to the other.
const ARC: Array<[number, number]> = [[1, 4], [3, 2], [7, 1], [11, 2], [13, 4]]
const COLORS = ['#40C4FF', '#FFC107', '#69F0AE', '#FF4081', '#B388FF']

export const conducting: AnimFn = (g, f) => {
  const phase = (f >> 1) % 2
  ARC.forEach(([x, y], k) => {
    if ((f + k) % 5 < 3) px(g, x, y, pick(COLORS, k))
  })
  crab(g, { dy: f % 2 === 0 ? 0 : -1, armL: phase === 0 ? -3 : 0, armR: phase === 0 ? 0 : -3, eyes: 'shut' })
}
