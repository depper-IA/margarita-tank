import { crab, px, type AnimFn } from './kit'

// Turn finished, waiting for the person: eyes wide and toward the viewer, one foot taps
// (2-frame loop), a small "!" above the head blinks.
export const waitingReply: AnimFn = (g, f) => {
  if ((f >> 1) % 2 === 0) {
    px(g, 7, 1, '#FFC107')
    px(g, 7, 2, '#FFC107')
    px(g, 7, 4, '#FFC107')
  }
  crab(g, {
    eyes: [[4, 7, 2, 3], [9, 7, 2, 3]],
    eyeDy: 0,
    lifted: [false, false, f % 2 === 0, false],
  })
}
