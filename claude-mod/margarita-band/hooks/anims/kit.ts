// Pixel toolkit shared by every animation. Coordinates are the ones of
// assets/svg-animations/clawd-static-base.svg (15 x 16 grid, torso at y=6).
export type Grid = Array<Array<string | null>>
export type Rect = [number, number, number, number]
// An animation paints frame `f` (a tick counter) onto a grid that already holds the ground shadow.
export type AnimFn = (g: Grid, f: number) => void

export const W = 15
export const H = 16
export const BODY = '#DE886D'
export const EYE = '#000000'
export const SHADOW = '#3A3A3A'

export function blank(): Grid {
  const g: Grid = Array.from({ length: H }, () => Array<string | null>(W).fill(null))
  rect(g, 3, 15, 9, 1, SHADOW)
  return g
}

export function rect(g: Grid, x: number, y: number, w: number, h: number, c: string): void {
  for (let j = Math.round(y); j < Math.round(y) + h; j += 1) {
    for (let i = Math.round(x); i < Math.round(x) + w; i += 1) {
      if (j >= 0 && j < H && i >= 0 && i < W) g[j]![i] = c
    }
  }
}

export function px(g: Grid, x: number, y: number, c: string): void {
  rect(g, x, y, 1, 1, c)
}

// Draws a small bitmap: every 'x' is a pixel.
export function glyph(g: Grid, x: number, y: number, rows: string[], c: string): void {
  rows.forEach((row, j) => {
    for (let i = 0; i < row.length; i += 1) if (row[i] === 'x') px(g, x + i, y + j, c)
  })
}

export const pick = <T>(list: readonly T[], f: number): T => list[((f % list.length) + list.length) % list.length]!

export type Eyes = 'open' | 'squint' | 'shut' | 'x' | Rect[]

export type CrabOpts = {
  dx?: number // whole upper body, columns
  dy?: number // whole upper body, rows (negative = up)
  legDx?: number
  armL?: number // vertical offset of the left arm from its rest row (negative = raised)
  armR?: number
  eyes?: Eyes
  eyeDx?: number
  eyeDy?: number
  lifted?: [boolean, boolean, boolean, boolean] // legs shortened by one pixel
  noLegs?: boolean
  noArms?: boolean
  body?: string
}

const LEGS = [3, 5, 9, 11]

// The base crab of clawd-static-base.svg with a few knobs.
export function crab(g: Grid, o: CrabOpts = {}): void {
  const dx = o.dx ?? 0
  const dy = o.dy ?? 0
  const body = o.body ?? BODY
  const top = 6 + dy

  if (!o.noLegs) {
    LEGS.forEach((x, i) => {
      const y0 = 13 + dy
      rect(g, x + (o.legDx ?? 0), y0, 1, 15 - y0 - (o.lifted?.[i] ? 1 : 0), body)
    })
  }
  rect(g, 2 + dx, top, 11, 7, body)
  if (!o.noArms) {
    rect(g, 0 + dx, 9 + dy + (o.armL ?? 0), 2, 2, body)
    rect(g, 13 + dx, 9 + dy + (o.armR ?? 0), 2, 2, body)
  }

  const ex = dx + (o.eyeDx ?? 0)
  const ey = dy + (o.eyeDy ?? 0)
  const eyes = o.eyes ?? 'open'
  if (eyes === 'open') {
    rect(g, 4 + ex, 8 + ey, 1, 2, EYE)
    rect(g, 10 + ex, 8 + ey, 1, 2, EYE)
  } else if (eyes === 'squint') {
    px(g, 4 + ex, 9 + ey, EYE)
    px(g, 10 + ex, 9 + ey, EYE)
  } else if (eyes === 'shut') {
    rect(g, 3 + ex, 9 + ey, 2, 1, EYE)
    rect(g, 10 + ex, 9 + ey, 2, 1, EYE)
  } else if (eyes === 'x') {
    for (const cx of [4, 10]) {
      glyph(g, cx - 1 + ex, 7 + ey, ['x.x', '.x.', 'x.x'], EYE)
    }
  } else {
    for (const [x, y, w, h] of eyes) rect(g, x + ex, y + ey, w, h, EYE)
  }
}

export type Run = { ch: string; fg?: string; bg?: string; n: number }

// Two pixel rows per text row with half blocks.
export function toRows(g: Grid): Run[][] {
  const rows: Run[][] = []
  for (let y = 0; y < H; y += 2) {
    const runs: Run[] = []
    for (let x = 0; x < W; x += 1) {
      const top = g[y]![x] ?? null
      const bottom = g[y + 1]![x] ?? null
      let cell: Omit<Run, 'n'>
      if (!top && !bottom) cell = { ch: ' ' }
      else if (top && top === bottom) cell = { ch: '█', fg: top }
      else if (top && !bottom) cell = { ch: '▀', fg: top }
      else if (!top && bottom) cell = { ch: '▄', fg: bottom }
      else cell = { ch: '▀', fg: top as string, bg: bottom as string }

      const last = runs[runs.length - 1]
      if (last && last.ch === cell.ch && last.fg === cell.fg && last.bg === cell.bg) last.n += 1
      else runs.push({ ...cell, n: 1 })
    }
    rows.push(runs)
  }
  return rows
}
