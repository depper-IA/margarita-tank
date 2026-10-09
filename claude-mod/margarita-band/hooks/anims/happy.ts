import { crab, pick, px, type AnimFn } from './kit'

// clawd-happy.svg (one shot at the end of a turn): bouncing, arms up, sparkles.
const SPOTS: Array<[number, number, string]> = [
  [2, 2, '#FFD700'], [12, 2, '#FFA000'], [13, 10, '#FFF59D'], [1, 10, '#FFC107'], [7, 1, '#FFF59D'],
]

export const happy: AnimFn = (g, f) => {
  SPOTS.forEach(([x, y, c], k) => {
    if ((f + k) % 3 === 2) return
    px(g, x, y, c)
    px(g, x - 1, y, c)
    px(g, x + 1, y, c)
    px(g, x, y - 1, c)
    px(g, x, y + 1, c)
  })
  const dy = pick([0, -1, -2, -1], f)
  crab(g, { dy, armL: f % 2 === 0 ? -3 : -2, armR: f % 2 === 0 ? -2 : -3, eyes: dy < -1 ? 'shut' : 'open' })
}
