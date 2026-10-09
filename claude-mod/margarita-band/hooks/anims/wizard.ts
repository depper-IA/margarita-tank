import { crab, pick, px, rect, type AnimFn, type Grid } from './kit'

// Pointed hat: cone rows plus a brim, as drawn in clawd-working-wizard.svg.
export function hat(g: Grid, ox: number, oy: number, cone = '#673AB7', brim = '#512DA8'): void {
  const widths = [1, 3, 3, 5, 7]
  widths.forEach((w, i) => rect(g, 7 - (w - 1) / 2 + ox, i + oy, w, 1, cone))
  px(g, 7 + ox, 3 + oy, '#FFC107')
  rect(g, 2 + ox, 5 + oy, 11, 1, brim)
}

const STARS = ['#FFC107', '#E040FB', '#40C4FF', '#69F0AE']

// clawd-working-wizard.svg: hat, wand, eyes shut then bursting open, stars rising.
export const wizard: AnimFn = (g, f) => {
  ;[0, 14, 1, 13].forEach((x, k) => {
    px(g, x, 12 - ((f * 2 + k * 3) % 12), pick(STARS, k))
  })
  const dy = f % 2 === 0 ? 0 : -1
  const armR = pick([-3, -2, -3, -1], f)
  crab(g, { dy, armL: f % 2 === 0 ? 1 : -1, armR, eyes: f % 4 < 2 ? 'shut' : 'open' })
  hat(g, 0, dy)
  const handY = 9 + dy + armR
  rect(g, 14, handY - 3, 1, 3, '#E0E0E0')
  px(g, 14, handY - 4, f % 2 === 0 ? '#FFEB3B' : '#FFFFFF')
}
