import { BODY, EYE, glyph, px, rect, type AnimFn, type Grid } from './kit'

// clawd-sleeping.svg: splooted crab, legs in the air, slow breathing, floating Zs.
export function sploot(g: Grid, squash: number, isAwake: boolean): void {
  for (const x of [3, 5, 9, 11]) px(g, x, 9 + squash, BODY)
  rect(g, 1, 10 + squash, 13, 5 - squash, BODY)
  rect(g, 0, 13, 1, 2, BODY)
  rect(g, 14, 13, 1, 2, BODY)
  if (isAwake) {
    rect(g, 4, 12 + squash, 1, 2, EYE)
    rect(g, 10, 12 + squash, 1, 2, EYE)
  } else {
    rect(g, 4, 12 + squash, 2, 1, EYE)
    rect(g, 10, 12 + squash, 2, 1, EYE)
  }
}

const Z = ['xxx', '.x.', 'xxx']
const SPOTS: Array<[number, number, string]> = [[11, 6, '#90A4AE'], [8, 3, '#B0BEC5'], [11, 0, '#CFD8DC']]

export const sleeping: AnimFn = (g, f) => {
  sploot(g, (f >> 1) % 2, false)
  const shown = 1 + ((f % 6) >> 1)
  SPOTS.slice(0, shown).forEach(([x, y, c]) => glyph(g, x, y, Z, c))
}
