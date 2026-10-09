import { crab, pick, rect, type AnimFn } from './kit'

// clawd-working-juggling.svg: three packets loop between the hands, eyes dart, body rocks.
// The daemon no longer emits this animation (juggling is retired); it is kept for /margarita.
const COLORS = ['#FFC107', '#40C4FF', '#FF4081']

export const juggling: AnimFn = (g, f) => {
  COLORS.forEach((c, k) => {
    const t = ((f + 2 * k) % 6) / 6
    const isHigh = t < 0.5
    const u = (isHigh ? t : t - 0.5) * 2
    const x = isHigh ? 1 + 11 * u : 12 - 11 * u
    const y = 8 - (isHigh ? 7 : 3) * Math.sin(Math.PI * u)
    rect(g, x, y, 2, 2, c)
  })
  crab(g, {
    dx: pick([0, 1, 0, -1], f),
    armL: f % 2 === 0 ? -2 : 0,
    armR: f % 2 === 0 ? 0 : -2,
    eyeDx: pick([-1, 0, 1, 0], f),
    eyeDy: pick([0, -1, 0, 0], f),
  })
}
