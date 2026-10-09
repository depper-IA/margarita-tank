import type { AnimName, Session } from '../types'

// Same rules as host/clawd_tank_daemon/daemon.py (_compute_display_state, _tool_to_anim).
export const TOOL_ANIMATION: Record<string, AnimName> = {
  Edit: 'typing',
  Write: 'typing',
  NotebookEdit: 'typing',
  Read: 'debugger',
  Grep: 'debugger',
  Glob: 'debugger',
  Bash: 'building',
  Agent: 'conducting',
  WebSearch: 'wizard',
  WebFetch: 'wizard',
  LSP: 'beacon',
}
export const WEB_TOOLS = ['WebSearch', 'WebFetch']
export const ASK_USER_QUESTION = 'AskUserQuestion'
export const LOW_BATTERY_USAGE_PCT = 90
// The daemon evicts a session with no event for 600 s; the firmware then shows "sleeping".
export const SLEEP_AFTER_MS = 600_000
// Not in the daemon: after this long idle the crab plays the "living" idle variant.
export const LIVING_AFTER_MS = 20_000
// Length of each oneshot, in 450 ms ticks.
export const ONESHOT_TICKS: Partial<Record<AnimName, number>> = { happy: 8, wake: 5, sweeping: 8 }

export function toolToAnim(tool: string): AnimName {
  if (tool.startsWith('mcp__')) return 'beacon'
  return TOOL_ANIMATION[tool] ?? 'typing'
}

export const NEW_SESSION: Session = {
  phase: 'idle',
  tool: '',
  subagents: [],
  lastEvent: 0,
  oneshot: '',
  oneshotLeft: 0,
  preview: '',
}

// State -> animation name. `usagePct` is the worst of the 5 h and weekly usage (0 when unknown).
export function selectAnim(s: Session, usagePct: number, now: number): AnimName {
  if (s.preview) return s.preview
  if (s.oneshot && s.oneshotLeft > 0) return s.oneshot

  const idleMs = now - s.lastEvent
  if (s.phase !== 'waiting' && s.phase !== 'ready' && idleMs >= SLEEP_AFTER_MS) return 'sleeping'

  switch (s.phase) {
    case 'waiting':
      return 'alert'
    case 'ready':
      return 'waiting_reply'
    case 'working':
      return toolToAnim(s.tool)
    case 'thinking':
      return 'thinking'
    case 'confused':
      return WEB_TOOLS.includes(s.tool) ? 'hat_mishap' : 'confused'
    case 'error':
      return 'dizzy'
    default:
      if (s.subagents.length > 0) return 'conducting'
      if (usagePct >= LOW_BATTERY_USAGE_PCT) return 'low_battery'
      return idleMs >= LIVING_AFTER_MS ? 'idle_living' : 'idle'
  }
}

// End of turn: happy oneshot, then waiting_reply until the next prompt (or session end).
export function onStop(s: Session): Session {
  return { ...s, phase: 'ready', oneshot: 'happy', oneshotLeft: ONESHOT_TICKS.happy ?? 8 }
}

export const onPromptSubmit = (s: Session): Session => ({ ...s, phase: 'thinking' })

// idle_prompt only means the person has not answered yet: it must not clear waiting_reply.
export const onIdlePrompt = (s: Session): Session =>
  s.phase === 'ready' ? s : { ...s, phase: 'idle', tool: '' }
