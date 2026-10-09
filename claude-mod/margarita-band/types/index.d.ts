// What the crab is doing, mirroring the Margarita Tank daemon's per-session states.
export type Phase = 'idle' | 'thinking' | 'working' | 'waiting' | 'confused' | 'error' | 'ready'

// Every firmware animation the pane can play (one pose function each in hooks/anims/).
export type AnimName =
  | 'idle' | 'idle_living' | 'sleeping' | 'wake' | 'happy' | 'thinking' | 'typing'
  | 'debugger' | 'building' | 'conducting' | 'wizard' | 'beacon' | 'juggling'
  | 'sweeping' | 'confused' | 'hat_mishap' | 'dizzy' | 'low_battery' | 'alert' | 'waiting_reply'

export type Session = {
  phase: Phase
  tool: string // last tool the session called ('' when none)
  subagents: string[] // ids of the subagents running now
  lastEvent: number // ms, clock.now() of the last event: drives the sleep timeout
  oneshot: AnimName | '' // animation that plays once, then yields to the state
  oneshotLeft: number // ticks left of the oneshot
  preview: AnimName | '' // forced by `/margarita <anim>` to look at any animation
}

// Art set the pane draws: the original 15x16 pose functions or the redesigned v2 frames.
export type Style = 'v1' | 'v2'

export type Usage = { session: number | null; weekly: number | null }

declare module 'claude-code' {
  interface PluginState {
    'margarita-band': { session: Session; frame: number; usage: Usage; style: Style }
  }
}
