import { crab, px, rect, type AnimFn } from './kit'

// clawd-working-building.svg: hard hat, hammer on an anvil. The SVG puts the anvil off to the
// side (x=17+), outside a 15-wide pane, so it is squeezed under the right arm here.
export const building: AnimFn = (g, f) => {
  const p = f % 4
  const isUp = p < 2
  const dy = isUp ? -1 : 0
  crab(g, { dy, armR: isUp ? -3 : 0, eyes: isUp ? 'open' : 'shut' })

  rect(g, 5, 1 + dy, 5, 1, '#FBC02D')
  rect(g, 4, 2 + dy, 7, 1, '#FBC02D')
  rect(g, 3, 3 + dy, 9, 2, '#FBC02D')
  rect(g, 1, 5 + dy, 13, 1, '#F9A825')

  rect(g, 12, 14, 3, 1, '#546E7A')
  px(g, 13, 13, p === 2 ? '#FFC107' : '#FF7043')
  if (isUp) {
    rect(g, 14, 2 + dy, 1, 6, '#795548')
    rect(g, 13, 1 + dy, 2, 2, '#9E9E9E')
  } else {
    rect(g, 14, 6, 1, 6, '#795548')
    rect(g, 13, 11, 2, 2, '#9E9E9E')
  }
  if (p === 2) {
    px(g, 12, 12, '#FFC107')
    px(g, 14, 10, '#FFC107')
  }
  if (p === 3) {
    px(g, 11, 11, '#FFC107')
    px(g, 14, 9, '#FFC107')
  }
  if (p === 1) px(g, 1, 7, '#40C4FF')
  if (p === 3) px(g, 0, 9, '#40C4FF')
}
