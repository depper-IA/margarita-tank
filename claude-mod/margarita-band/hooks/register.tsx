import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { AnimName, Session, Usage } from '../types'
import { ANIMS, drawAnim } from './anims'
import { toRows } from './anims/kit'
import {
  ASK_USER_QUESTION,
  LOW_BATTERY_USAGE_PCT,
  NEW_SESSION,
  ONESHOT_TICKS,
  onIdlePrompt,
  onPromptSubmit,
  onStop,
  selectAnim,
} from './select'

const session = atom({ plugin: 'margarita-band', key: 'session' } as const, NEW_SESSION)
const frame = atom({ plugin: 'margarita-band', key: 'frame' } as const, 0)
const usage = atom(
  { plugin: 'margarita-band', key: 'usage' } as const,
  { session: null, weekly: null } as Usage,
)

const PANE = 'margarita'
const TICK_MS = 450
const BATTERY_COLOR = '#FF4444'

const LABELS: Record<AnimName, string> = {
  idle: 'descansando',
  idle_living: 'descansando',
  sleeping: 'zzz…',
  wake: 'despertando',
  happy: '¡listo!',
  thinking: 'pensando',
  typing: 'escribiendo',
  debugger: 'investigando',
  building: 'construyendo',
  conducting: 'dirigiendo',
  wizard: 'en la web',
  beacon: 'señal MCP',
  juggling: 'malabares',
  sweeping: 'compactando',
  confused: 'confundido',
  hat_mishap: '¡mi sombrero!',
  dizzy: 'mareado',
  low_battery: 'batería baja',
  alert: 'te necesito',
  waiting_reply: 'esperando tu respuesta',
}

let startedAt = 0
let toolCalls = 0
let isTicking = false

const percent = (v: unknown): number | null => {
  const n = Number(v)
  return v === undefined || v === null || Number.isNaN(n) ? null : n
}

const worstUsage = (u: Usage): number => Math.max(u.session ?? 0, u.weekly ?? 0)

// Same cache the Margarita Tank daemon reads (written by its statusLine bridge).
async function refreshUsage($: EngineInterface): Promise<void> {
  try {
    // HOME on macOS and Linux; Windows usually has only USERPROFILE. The names are literals:
    // `claude plugin validate` reads them off the source.
    const home = (await $.env.get('HOME')) || (await $.env.get('USERPROFILE'))
    if (!home) return
    const raw = await $.fs.read(`${home}/.clawd-tank/statusline-cache.json`)
    const limits = JSON.parse(String(raw)).rate_limits ?? {}
    const next: Usage = {
      session: percent(limits.five_hour?.used_percentage),
      weekly: percent(limits.seven_day?.used_percentage),
    }
    await update($, usage, () => next)
  } catch {
    // Cache missing or unreadable: keep the last known values.
  }
}

// Applies an event to the session like the daemon does: stamps the event time and, when the
// crab was asleep, plays the wake oneshot first (the firmware does that when leaving sleep).
async function touch($: EngineInterface, change: (s: Session) => Session): Promise<void> {
  const now = await $.clock.now()
  const u = await read($, usage)
  await update($, session, s => {
    const wasAsleep = selectAnim({ ...s, preview: '' }, worstUsage(u), now) === 'sleeping'
    const next: Session = { ...change(s), lastEvent: now }
    if (wasAsleep && !(next.oneshot && next.oneshotLeft > 0)) {
      return { ...next, oneshot: 'wake' as const, oneshotLeft: ONESHOT_TICKS.wake ?? 5 }
    }
    return next
  })
}

const withOneshot = (s: Session, name: AnimName): Session => ({
  ...s,
  oneshot: name,
  oneshotLeft: ONESHOT_TICKS[name] ?? 6,
})

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await refreshUsage($)
    await $.command.register({
      name: 'margarita',
      description: 'Muestra a Clawd en un panel lateral',
      argumentHint: '[animación|auto]',
    })
    void $.ui.open({ id: PANE, title: 'Margarita', columns: 20 })
    await touch($, s => ({ ...s, phase: 'idle' as const, tool: '', subagents: [] }))

    if (!isTicking) {
      isTicking = true
      $.clock.every(TICK_MS, async () => {
        await update($, frame, n => n + 1)
        await update($, session, s => (s.oneshotLeft > 0 ? { ...s, oneshotLeft: s.oneshotLeft - 1 } : s))
      })
    }

    return next(e)
  })

  on('session.end', async ($, e, next) => {
    // The daemon drops the session and the firmware falls asleep.
    await update($, session, s => ({ ...s, phase: 'idle' as const, tool: '', subagents: [], oneshotLeft: 0, lastEvent: 0 }))
    return next(e)
  })

  on('command.run', { command: 'margarita' }, async ($, e) => {
    await $.ui.open({ id: PANE, title: 'Margarita', columns: 20 })
    const arg = String(e.args ?? '').trim()
    const names = Object.keys(ANIMS)
    if (arg && names.includes(arg)) {
      await update($, session, s => ({ ...s, preview: arg as AnimName }))
      return { text: `Margarita: viendo "${arg}". /margarita auto para volver.` }
    }
    if (arg === 'auto') {
      await update($, session, s => ({ ...s, preview: '' as const }))
      return { text: 'Margarita: modo automático.' }
    }
    return { text: `Margarita abierta. Animaciones: ${names.join(', ')}.` }
  })

  on('prompt.submit', async ($, e, next) => {
    startedAt = await $.clock.now()
    toolCalls = 0
    await touch($, onPromptSubmit)
    await refreshUsage($)
    return next(e)
  })

  on('tool.call', async ($, e, next) => {
    toolCalls += 1
    const tool = String(e.tool)
    await touch($, s => ({ ...s, phase: tool === ASK_USER_QUESTION ? 'waiting' : 'working', tool }))
    return next(e)
  })

  // A permission prompt blocks on the person, like AskUserQuestion: the alert animation.
  on('classic.PermissionRequest', async ($, e, next) => {
    await touch($, s => ({ ...s, phase: 'waiting', tool: e.tool_name }))
    return next(e)
  })

  // Only AskUserQuestion's answer matters (the daemon scopes this hook to it).
  on('classic.PostToolUse', async ($, e, next) => {
    if (e.tool_name === ASK_USER_QUESTION) {
      await touch($, s => (s.phase === 'waiting' ? { ...s, phase: 'thinking' } : s))
    }
    return next(e)
  })

  on('classic.PostToolUseFailure', async ($, e, next) => {
    await touch($, s => ({ ...s, phase: 'confused', tool: e.tool_name }))
    return next(e)
  })

  on('classic.PreCompact', async ($, e, next) => {
    await touch($, s => withOneshot(s, 'sweeping'))
    return next(e)
  })

  // End of turn: idle again, plus the happy oneshot.
  on('classic.Stop', async ($, e, next) => {
    await touch($, onStop)
    await refreshUsage($)
    return next(e)
  })

  on('classic.StopFailure', async ($, e, next) => {
    await touch($, s => ({ ...s, phase: 'error' }))
    return next(e)
  })

  // idle_prompt only: the session just waits for the person.
  on('classic.Notification', async ($, e, next) => {
    if (e.notification_type === 'idle_prompt') {
      await touch($, onIdlePrompt)
    }
    return next(e)
  })

  on('classic.SubagentStart', async ($, e, next) => {
    if (e.agent_id) {
      await touch($, s => ({
        ...s,
        subagents: s.subagents.includes(e.agent_id) ? s.subagents : [...s.subagents, e.agent_id],
      }))
    }
    return next(e)
  })

  // A subagent finished: celebrate on the parent, as the daemon does.
  on('classic.SubagentStop', async ($, e, next) => {
    await touch($, s => {
      if (!s.subagents.includes(e.agent_id)) return s
      return withOneshot({ ...s, subagents: s.subagents.filter(id => id !== e.agent_id) }, 'happy')
    })
    return next(e)
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const s = await read($, session)
    const f = await read($, frame)
    const u = await read($, usage)
    const now = await $.clock.now()
    const { Box, Text } = $.ui.resolve(e)

    const worst = worstUsage(u)
    const anim = selectAnim(s, worst, now)
    const total = ONESHOT_TICKS[anim]
    // A oneshot plays from its first frame; a previewed oneshot loops.
    const step = total === undefined ? f : s.preview ? f % total : total - s.oneshotLeft
    const rows = toRows(drawAnim(anim, step))

    const elapsed = startedAt > 0 ? Math.round((now - startedAt) / 1000) : 0
    const isBusy = s.phase === 'working' || s.phase === 'thinking'
    const detail = s.phase === 'working' && s.tool ? s.tool : isBusy ? `${toolCalls} tools · ${elapsed}s` : ''
    const isHot = worst >= LOW_BATTERY_USAGE_PCT

    // Fill the pane's height so the crab sits in the middle instead of the top.
    const height = e.viewport?.rows

    return (
      <Box flexDirection="column" alignItems="center" justifyContent="center" height={height}>
        <Box flexDirection="column">
          {rows.map((runs, i) => (
            <Box key={`r${i}`} flexDirection="row">
              {runs.map((r, j) => (
                <Text key={`p${j}`} color={r.fg} backgroundColor={r.bg}>
                  {r.ch.repeat(r.n)}
                </Text>
              ))}
            </Box>
          ))}
        </Box>
        <Box flexDirection="column" alignItems="center" marginTop={1}>
          <Text bold>{LABELS[anim]}</Text>
          {detail ? <Text dimColor>{detail}</Text> : null}
          {s.subagents.length > 0 ? <Text dimColor>{`${s.subagents.length} subagentes`}</Text> : null}
          {isHot ? <Text color={BATTERY_COLOR}>{`batería ${Math.round(worst)}%`}</Text> : null}
          {s.preview ? <Text dimColor>vista previa</Text> : null}
        </Box>
      </Box>
    )
  })
}
