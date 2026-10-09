import { crab, pick, px, rect, type AnimFn } from './kit'

// clawd-working-sweeping.svg (compact): the crab sweeps dust with a push broom.
export const sweeping: AnimFn = (g, f) => {
  crab(g, {
    dx: pick([0, -1, -1, 0], f),
    armR: pick([0, 1, 2, 1], f),
    eyes: [[5, 9, 1, 1], [11, 8, 1, 2]],
  })
  const bx = 14 - pick([0, 1, 2, 1], f)
  rect(g, bx, 4, 1, 10, '#795548')
  rect(g, bx - 2, 14, 4, 2, '#FFC107')
  px(g, bx - 3 - (f % 4), 13 + (f % 2), '#9E9E9E')
  px(g, bx - 5 - (f % 3), 14, '#B0BEC5')
}
