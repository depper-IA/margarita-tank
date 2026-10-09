import { crab, px, rect, type AnimFn } from './kit'

// clawd-working-thinking.svg: slow sway, one arm taps the chin, a bubble loads its three dots.
export const thinking: AnimFn = (g, f) => {
  rect(g, 6, 0, 8, 4, '#FFFFFF')
  for (const [x, y] of [[6, 0], [13, 0], [6, 3], [13, 3]] as const) g[y]![x] = null
  px(g, 5, 4, '#FFFFFF')
  px(g, 4, 5, '#FFFFFF')
  const dots = f % 4
  ;[7, 9, 11].forEach((x, i) => {
    if (dots > i) px(g, x, 2, '#0082FC')
  })
  crab(g, {
    dx: (f >> 1) % 2,
    armL: 1,
    armR: f % 2 === 0 ? -1 : -2,
    eyes: f % 10 === 9 ? 'shut' : [[5, 7, 1, 2], [11, 7, 1, 2]],
  })
}
