import type { AnimName, Style } from '../types'
import { drawAnim } from './anims'
import { toRows, type Run } from './anims/kit'
import { ANIMS_V2, V2_MAX_HEIGHT, V2_MAX_WIDTH } from './anims-v2'
import { decodeFrame, frameIndex } from './anims-v2/decode'
import type { V2Anim } from './anims-v2/types'
import { ONESHOT_TICKS } from './select'

export const DEFAULT_STYLE: Style = 'v2'
export const V1_COLUMNS = 20
// Free columns around the widest v2 frame.
export const V2_MARGIN = 2
// Timer period: the finest frame step (10 fps = 100 ms) needs a tick at most every 125 ms.
export const TICK_MS = 125
// The v1 pose functions still advance once per 450 ms, as before.
export const V1_TICK_MS = 450

export const paneColumns = (style: Style): number => (style === 'v2' ? V2_MAX_WIDTH + V2_MARGIN : V1_COLUMNS)

// Text rows the crab area keeps, so the labels below do not move between animations.
export const crabRowCount = (style: Style): number => (style === 'v2' ? V2_MAX_HEIGHT / 2 : 8)

export const v2For = (name: AnimName, style: Style): V2Anim | undefined => (style === 'v2' ? ANIMS_V2[name] : undefined)

// Oneshots (happy, wake, sweeping) play once and hold their last frame; a previewed one loops.
export const loops = (name: AnimName, preview: boolean): boolean => preview || ONESHOT_TICKS[name] === undefined

// Which stored v2 frame shows `elapsedMs` after the animation began.
export const v2Index = (a: V2Anim, name: AnimName, elapsedMs: number, preview: boolean): number =>
  frameIndex(a, elapsedMs, loops(name, preview))

// Half-block rows of the crab: v2 art when the style and animation have it, else the v1 pose.
export function crabRows(
  name: AnimName,
  style: Style,
  v1Step: number,
  elapsedMs: number,
  preview: boolean,
): { rows: Run[][]; width: number } {
  const a = v2For(name, style)
  if (a) return { rows: toRows(decodeFrame(a, v2Index(a, name, elapsedMs, preview))), width: a.width }
  return { rows: toRows(drawAnim(name, v1Step)), width: 15 }
}

export type Command =
  | { kind: 'style'; style: Style }
  | { kind: 'style-help' }
  | { kind: 'preview'; anim: AnimName }
  | { kind: 'auto' }
  | { kind: 'help' }

// `/margarita style v1|v2`, `/margarita <anim>`, `/margarita auto`; anything else is help.
export function parseCommand(arg: string, names: readonly string[]): Command {
  const parts = arg.trim().split(/\s+/).filter(Boolean)
  if (parts[0] === 'style') {
    return parts[1] === 'v1' || parts[1] === 'v2' ? { kind: 'style', style: parts[1] } : { kind: 'style-help' }
  }
  if (parts.length === 1 && parts[0] === 'auto') return { kind: 'auto' }
  if (parts.length === 1 && parts[0] && names.includes(parts[0])) return { kind: 'preview', anim: parts[0] as AnimName }
  return { kind: 'help' }
}
