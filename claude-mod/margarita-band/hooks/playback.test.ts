import { expect, test } from 'claude-code/testing'

import { ANIMS } from './anims'
import { ANIMS_V2, V2_MAX_HEIGHT, V2_MAX_WIDTH } from './anims-v2'
import { decodeFrame, frameIndex, totalHolds } from './anims-v2/decode'
import type { V2Anim } from './anims-v2/types'
import {
  crabRowCount,
  crabRows,
  loops,
  paneColumns,
  parseCommand,
  v2For,
  v2Index,
  V2_MARGIN,
} from './playback'

// 2 colours, 3 stored frames lasting 2 + 1 + 3 source frames at 10 fps (100 ms each).
const TINY: V2Anim = {
  fps: 10,
  width: 3,
  height: 2,
  palette: ['#FF0000', '#00FF00'],
  frames: [['a/b2', 2], ['.a2/b', 1], ['/', 3]],
}

test('frame index follows time and holds', () => {
  expect(totalHolds(TINY)).toBe(6)
  const at = (ms: number) => frameIndex(TINY, ms, true)
  expect([0, 99, 100, 199, 200, 299, 300, 599].map(at)).toEqual([0, 0, 0, 0, 1, 1, 2, 2])
  // wraps after 600 ms
  expect([600, 799, 800, 1000].map(at)).toEqual([0, 0, 1, 2])
  // oneshot: holds the last frame
  expect(frameIndex(TINY, 5000, false)).toBe(2)
  // never negative, even with a clock that moved back
  expect(frameIndex(TINY, -50, true)).toBe(0)
})

test('frame index uses the animation fps', () => {
  const slow = { ...TINY, fps: 6 }
  // 6 fps: a source frame lasts 166.67 ms; step 2 starts at 333.3 ms
  expect([0, 166, 333, 334, 499, 500].map(ms => frameIndex(slow, ms, true))).toEqual([0, 0, 0, 1, 1, 2])
})

test('decodes rows, runs and transparent cells', () => {
  expect(decodeFrame(TINY, 0)).toEqual([
    ['#FF0000', null, null],
    ['#00FF00', '#00FF00', null],
  ])
  expect(decodeFrame(TINY, 1)).toEqual([
    [null, '#FF0000', '#FF0000'],
    ['#00FF00', null, null],
  ])
  expect(decodeFrame(TINY, 2)).toEqual([[null, null, null], [null, null, null]])
})

test('every generated animation is well formed', () => {
  const entries = Object.entries(ANIMS_V2) as Array<[string, V2Anim]>
  expect(entries.length).toBe(17) // 16 animations + the idle_living alias
  for (const [name, a] of entries) {
    expect(a.height % 2, name).toBe(0)
    expect(a.width <= V2_MAX_WIDTH && a.height <= V2_MAX_HEIGHT, name).toBe(true)
    expect(a.palette.length <= 52, name).toBe(true)
    a.frames.forEach((f, i) => {
      expect(f[1] >= 1, name).toBe(true)
      const grid = decodeFrame(a, i)
      expect(grid.length, `${name}#${i}`).toBe(a.height)
      expect(grid.every(r => r.length === a.width), `${name}#${i}`).toBe(true)
    })
  }
  expect(V2_MAX_WIDTH).toBe(Math.max(...entries.map(([, a]) => a.width)))
})

test('firmware fps per animation', () => {
  const fps: Record<string, number> = {
    idle: 6, sleeping: 6, low_battery: 6, hat_mishap: 6,
    thinking: 8, typing: 8, debugger: 8, building: 8, conducting: 8, waiting_reply: 8,
    wake: 8, confused: 8, dizzy: 8, sweeping: 8, happy: 10, alert: 10,
  }
  for (const [name, f] of Object.entries(fps)) expect(ANIMS_V2[name as keyof typeof ANIMS_V2]?.fps).toBe(f)
})

test('animations without v2 art fall back to the v1 poses', () => {
  for (const name of ['wizard', 'beacon', 'juggling'] as const) {
    expect(v2For(name, 'v2')).toBeUndefined()
    const { rows, width } = crabRows(name, 'v2', 0, 0, false)
    expect(width).toBe(15)
    expect(rows.length).toBe(8)
  }
  // the v2 idle art is the living idle
  expect(v2For('idle_living', 'v2')).toBe(v2For('idle', 'v2'))
})

test('style v1 never uses v2 art, v2 does', () => {
  expect(v2For('idle', 'v1')).toBeUndefined()
  expect(crabRows('idle', 'v1', 0, 0, false).width).toBe(15)
  const v2 = crabRows('idle', 'v2', 0, 0, false)
  expect(v2.width).toBe(ANIMS_V2.idle!.width)
  expect(v2.rows.length).toBe(ANIMS_V2.idle!.height / 2)
  // v2 rows are as wide as the animation
  const cells = v2.rows[0]!.reduce((n, r) => n + r.n, 0)
  expect(cells).toBe(v2.width)
})

test('half blocks: top pixel is foreground, bottom background', () => {
  // happy at t=0 has its crab on the lower rows; find a two-colour cell and check both colours
  const rows = crabRows('idle', 'v2', 0, 0, false).rows
  const mixed = rows.flat().find(r => r.ch === '▀' && r.bg !== undefined)
  expect(mixed?.fg).toBeDefined()
  const grid = decodeFrame(ANIMS_V2.idle!, 0)
  const y = rows.findIndex(row => row.some(r => r === mixed))
  let x = 0
  for (const r of rows[y]!) {
    if (r === mixed) break
    x += r.n
  }
  expect(grid[2 * y]![x]).toBe(mixed!.fg)
  expect(grid[2 * y + 1]![x]).toBe(mixed!.bg)
})

test('oneshots hold, previews and state animations loop', () => {
  expect(loops('happy', false)).toBe(false)
  expect(loops('happy', true)).toBe(true)
  expect(loops('idle', false)).toBe(true)
  const happy = ANIMS_V2.happy!
  expect(v2Index(happy, 'happy', 60_000, false)).toBe(happy.frames.length - 1)
})

test('pane columns fit the widest v2 frame plus the margin', () => {
  expect(paneColumns('v2')).toBe(V2_MAX_WIDTH + V2_MARGIN)
  expect(paneColumns('v1')).toBe(20)
  expect(crabRowCount('v2')).toBe(V2_MAX_HEIGHT / 2)
  expect(crabRowCount('v1')).toBe(8)
})

test('/margarita command parsing', () => {
  const names = Object.keys(ANIMS)
  expect(parseCommand('style v1', names)).toEqual({ kind: 'style', style: 'v1' })
  expect(parseCommand(' style   v2 ', names)).toEqual({ kind: 'style', style: 'v2' })
  expect(parseCommand('style', names)).toEqual({ kind: 'style-help' })
  expect(parseCommand('style v3', names)).toEqual({ kind: 'style-help' })
  expect(parseCommand('auto', names)).toEqual({ kind: 'auto' })
  expect(parseCommand('happy', names)).toEqual({ kind: 'preview', anim: 'happy' })
  expect(parseCommand('nope', names)).toEqual({ kind: 'help' })
  expect(parseCommand('', names)).toEqual({ kind: 'help' })
})
