import { crab, px, rect, type AnimFn } from './kit'

// clawd-notification.svg: the firmware's "alert" (AskUserQuestion / permission prompt):
// the crab startles, squashes, then jumps to get attention under a red "!".
export const alert: AnimFn = (g, f) => {
  rect(g, 7, 0, 1, 2, '#FF3D00')
  px(g, 7, 3, '#FF3D00')
  const p = f % 4
  if (p === 0) crab(g, { dx: 1, eyeDx: 1 })
  else if (p === 1) crab(g, { dy: 1, eyes: 'shut' })
  else if (p === 2) crab(g, { dy: -2, armL: -3, armR: -3 })
  else crab(g, { armL: -2, armR: -2 })
}
