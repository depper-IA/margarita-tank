import { crab, glyph, pick, type AnimFn } from './kit'

// clawd-working-confused.svg (tool failure): head tilts side to side, question marks pop up.
const QUESTION = ['xxx', '..x', '.x.', '...', '.x.']

export const confused: AnimFn = (g, f) => {
  const phase = (f >> 1) % 2
  glyph(g, phase === 0 ? 0 : 12, f % 2, QUESTION, phase === 0 ? '#40C4FF' : '#FFC107')
  crab(g, {
    dx: pick([-1, 0, 1, 0], f),
    armL: -2,
    eyeDx: pick([-1, -1, 1, 1], f),
    eyes: f % 7 === 6 ? 'shut' : 'open',
  })
}
