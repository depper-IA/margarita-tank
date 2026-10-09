import { crab, pick, px, rect, type AnimFn } from './kit'

// clawd-working-debugger.svg: hunched crab sneaks along, one eye behind a magnifying glass.
export const debuggerAnim: AnimFn = (g, f) => {
  const dx = pick([-1, 0, 1, 0], f)
  crab(g, {
    dx,
    dy: 1,
    legDx: dx,
    armL: -1,
    eyes: [[4, 9, 1, 1]],
    lifted: [f % 2 === 0, f % 2 === 1, f % 2 === 0, f % 2 === 1],
  })
  const gx = 8 + dx
  const gy = 4 + (f % 2)
  rect(g, gx, gy, 6, 6, '#546E7A')
  rect(g, gx + 1, gy + 1, 4, 4, '#B3E5FC')
  px(g, gx + 1, gy + 1, '#FFFFFF')
  rect(g, gx + 3, gy + 2, 1, 2, '#000000')
  px(g, gx + 5, gy + 6, '#795548')
}
