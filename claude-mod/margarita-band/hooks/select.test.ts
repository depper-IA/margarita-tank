import { expect, test } from 'claude-code/testing'

import type { Session } from '../types'
import { NEW_SESSION, onIdlePrompt, onPromptSubmit, onStop, selectAnim } from './select'

const NOW = 1_000_000
const at = (patch: Partial<Session>): Session => ({ ...NEW_SESSION, lastEvent: NOW, ...patch })
const pick = (patch: Partial<Session>, usage = 0, now = NOW) => selectAnim(at(patch), usage, now)

test('tools map to the daemon animations', () => {
  const cases: Array<[string, string]> = [
    ['Edit', 'typing'], ['Write', 'typing'], ['NotebookEdit', 'typing'],
    ['Read', 'debugger'], ['Grep', 'debugger'], ['Glob', 'debugger'],
    ['Bash', 'building'], ['Agent', 'conducting'],
    ['WebSearch', 'wizard'], ['WebFetch', 'wizard'], ['LSP', 'beacon'],
    ['mcp__codegraph__codegraph_explore', 'beacon'], ['SomethingNew', 'typing'],
  ]
  for (const [tool, anim] of cases) expect(pick({ phase: 'working', tool })).toBe(anim)
})

test('thinking, waiting and error states', () => {
  expect(pick({ phase: 'thinking' })).toBe('thinking')
  expect(pick({ phase: 'waiting', tool: 'AskUserQuestion' })).toBe('alert')
  expect(pick({ phase: 'error' })).toBe('dizzy')
})

test('a failed tool is confused, a failed web tool loses its hat', () => {
  expect(pick({ phase: 'confused', tool: 'Bash' })).toBe('confused')
  expect(pick({ phase: 'confused', tool: 'WebSearch' })).toBe('hat_mishap')
  expect(pick({ phase: 'confused', tool: 'WebFetch' })).toBe('hat_mishap')
})

test('idle: conducting with subagents, low battery at 90%, living after a while', () => {
  expect(pick({})).toBe('idle')
  expect(pick({ subagents: ['a'] })).toBe('conducting')
  expect(pick({ subagents: ['a'] }, 95)).toBe('conducting')
  expect(pick({}, 89)).toBe('idle')
  expect(pick({}, 90)).toBe('low_battery')
  expect(pick({}, 0, NOW + 30_000)).toBe('idle_living')
})

test('subagents never override a busy session', () => {
  expect(pick({ phase: 'working', tool: 'Bash', subagents: ['a', 'b'] })).toBe('building')
  expect(pick({ phase: 'thinking', subagents: ['a'] })).toBe('thinking')
})

test('low battery only replaces idle', () => {
  expect(pick({ phase: 'working', tool: 'Bash' }, 99)).toBe('building')
  expect(pick({ phase: 'thinking' }, 99)).toBe('thinking')
})

test('a oneshot wins until it runs out', () => {
  expect(pick({ phase: 'working', tool: 'Bash', oneshot: 'happy', oneshotLeft: 3 })).toBe('happy')
  expect(pick({ phase: 'idle', oneshot: 'sweeping', oneshotLeft: 1 })).toBe('sweeping')
  expect(pick({ phase: 'idle', oneshot: 'happy', oneshotLeft: 0 })).toBe('idle')
})

test('no event for 10 minutes means sleeping, except while waiting for the user', () => {
  expect(pick({ phase: 'working', tool: 'Bash' }, 0, NOW + 600_000)).toBe('sleeping')
  expect(pick({}, 99, NOW + 600_000)).toBe('sleeping')
  expect(pick({ phase: 'waiting' }, 0, NOW + 600_000)).toBe('alert')
  expect(pick({}, 0, NOW + 599_000)).toBe('idle_living')
})

test('a preview overrides everything', () => {
  expect(pick({ phase: 'working', tool: 'Bash', preview: 'juggling', oneshot: 'happy', oneshotLeft: 2 })).toBe('juggling')
})

test('Stop: happy oneshot, then waiting_reply until the next prompt', () => {
  const s = onStop(at({ phase: 'working', tool: 'Bash' }))
  expect(selectAnim(s, 0, NOW)).toBe('happy')
  expect(selectAnim({ ...s, oneshotLeft: 0 }, 0, NOW)).toBe('waiting_reply')
  expect(selectAnim({ ...s, oneshotLeft: 0 }, 99, NOW + 20_000)).toBe('waiting_reply')
  expect(selectAnim({ ...s, oneshotLeft: 0, subagents: ['a'] }, 0, NOW)).toBe('waiting_reply')
})

test('prompt.submit leaves waiting_reply for thinking', () => {
  const s = onPromptSubmit({ ...onStop(at({})), oneshotLeft: 0 })
  expect(s.phase).toBe('thinking')
  expect(selectAnim(s, 0, NOW)).toBe('thinking')
})

test('waiting_reply never goes to sleep', () => {
  const s = { ...onStop(at({})), oneshotLeft: 0 }
  expect(selectAnim(s, 0, NOW + 3_600_000)).toBe('waiting_reply')
})

test('alert and error keep priority over waiting_reply', () => {
  const ready = { ...onStop(at({})), oneshotLeft: 0 }
  expect(selectAnim({ ...ready, phase: 'waiting', tool: 'AskUserQuestion' }, 0, NOW)).toBe('alert')
  expect(selectAnim({ ...ready, phase: 'error' }, 0, NOW)).toBe('dizzy')
})

test('idle_prompt does not clear waiting_reply, but still idles other phases', () => {
  const ready = { ...onStop(at({})), oneshotLeft: 0 }
  expect(selectAnim(onIdlePrompt(ready), 0, NOW)).toBe('waiting_reply')
  expect(onIdlePrompt(at({ phase: 'working', tool: 'Bash' })).phase).toBe('idle')
})

test('a preview still shows waiting_reply', () => {
  expect(pick({ preview: 'waiting_reply' })).toBe('waiting_reply')
})
