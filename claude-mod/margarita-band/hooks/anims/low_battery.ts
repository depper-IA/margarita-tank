import { crab, pick, px, rect, type AnimFn } from './kit'

// clawd-idle-low-battery.svg (idle with usage >= 90%): drowsy crab, red battery blinking.
export const lowBattery: AnimFn = (g, f) => {
  const red = '#FF4444'
  rect(g, 6, 0, 7, 1, red)
  rect(g, 6, 3, 7, 1, red)
  rect(g, 6, 1, 1, 2, red)
  rect(g, 12, 1, 1, 2, red)
  rect(g, 13, 1, 1, 2, red)
  if (f % 2 === 0) rect(g, 7, 1, 1, 2, red)
  crab(g, { dy: pick([0, 0, 1, 1], f), armL: 1, armR: 1, eyes: pick(['open', 'squint', 'shut', 'squint'] as const, f) })
}
