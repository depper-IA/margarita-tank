import { crab, pick, px, type AnimFn } from './kit'

// clawd-dizzy.svg (the turn ended in an API error): swaying crab, X eyes, stars orbiting its head.
export const dizzy: AnimFn = (g, f) => {
  for (let k = 0; k < 3; k += 1) {
    const a = f * 0.9 + k * 2.094
    px(g, 7 + 5 * Math.cos(a), 3 + 1.5 * Math.sin(a), Math.sin(a) < 0 ? '#A68B00' : '#FFD54F')
  }
  crab(g, { dx: pick([-1, 0, 1, 0], f), eyes: 'x', armL: f % 2, armR: (f + 1) % 2 })
}
