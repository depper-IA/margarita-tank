import { crab, px, rect, type AnimFn } from './kit'

// clawd-working-beacon.svg (MCP tools): antenna with a blinking tip, signal rings expanding.
const RING = ['#40C4FF', '#1E6A8A']

export const beacon: AnimFn = (g, f) => {
  ;[0, 1].forEach(back => {
    const r = 2 + 2 * (((f - back) % 3 + 3) % 3)
    for (let a = 0; a <= 180; a += 20) {
      const rad = (a * Math.PI) / 180
      px(g, 7 + r * Math.cos(rad), 3 - r * 0.8 * Math.sin(rad), RING[back]!)
    }
  })
  const dy = f % 2 === 0 ? 0 : -1
  crab(g, { dy, armL: -1, armR: -1 })
  rect(g, 7, 2 + dy, 1, 4 - dy, '#78909C')
  px(g, 7, 1 + dy, f % 2 === 0 ? '#FF5252' : '#FFFFFF')
}
