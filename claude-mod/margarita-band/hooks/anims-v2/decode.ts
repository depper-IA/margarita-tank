import type { Grid } from '../anims/kit'
import type { V2Anim } from './types'

const ALPHABET = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'

// Total length in source frames (1/fps each).
export const totalHolds = (a: V2Anim): number => a.frames.reduce((n, f) => n + f[1], 0)

// Which stored frame is on screen `elapsedMs` after the animation started.
// `loop` wraps around; otherwise the last frame is held (oneshots).
export function frameIndex(a: V2Anim, elapsedMs: number, loop: boolean): number {
  const total = totalHolds(a)
  const raw = Math.floor((Math.max(0, elapsedMs) * a.fps) / 1000)
  const step = loop ? raw % total : Math.min(raw, total - 1)
  let acc = 0
  for (let i = 0; i < a.frames.length; i += 1) {
    acc += a.frames[i]![1]
    if (step < acc) return i
  }
  return a.frames.length - 1
}

// Decodes one stored frame to a width x height grid of colours (null = transparent).
export function decodeFrame(a: V2Anim, index: number): Grid {
  const rle = a.frames[index]![0]
  return rle.split('/').map(row => {
    const cells: Array<string | null> = []
    let i = 0
    while (i < row.length) {
      const c = row[i]!
      i += 1
      let j = i
      while (j < row.length && row.charCodeAt(j) >= 48 && row.charCodeAt(j) <= 57) j += 1
      const n = j > i ? Number(row.slice(i, j)) : 1
      i = j
      const color = c === '.' ? null : (a.palette[ALPHABET.indexOf(c)] ?? null)
      for (let k = 0; k < n; k += 1) cells.push(color)
    }
    while (cells.length < a.width) cells.push(null)
    return cells
  })
}
