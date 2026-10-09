import { expect, mock, test } from 'claude-code/testing'
import type { Engine, On } from 'claude-code/testing'

const CACHE = JSON.stringify({
  rate_limits: { five_hour: { used_percentage: 91 }, seven_day: { used_percentage: 12 } },
})

// Submitting a prompt makes the mod read the usage cache the Margarita Tank daemon's statusLine
// bridge writes. The test answers that read at the bottom of the chain and records where it looked.
async function pathsReadAfterPrompt($: Engine, on: On, variables: Record<string, string>) {
  mock.clock(on)
  mock.env(on, variables)
  const paths: string[] = []
  on('fs.read', async (_$, e) => {
    paths.push(e.path)
    return { value: CACHE }
  })
  on('prompt.submit', async (_$, e) => ({ text: e.text }))
  await $.prompt.submit({ text: 'hola' })
  return paths
}

// The engine resolves a path against the host it runs on, so these use absolute POSIX folders even
// for the Windows variable: a drive letter would be a relative path on the machine running the tests.
test('HOME locates the usage cache', async ($, on) => {
  const paths = await pathsReadAfterPrompt($, on, { HOME: '/Users/ana' })
  expect(paths).toEqual(['/Users/ana/.clawd-tank/statusline-cache.json'])
})

test('on Windows, where HOME is usually unset, USERPROFILE locates it', async ($, on) => {
  const paths = await pathsReadAfterPrompt($, on, { USERPROFILE: '/Users/ana-profile' })
  expect(paths).toEqual(['/Users/ana-profile/.clawd-tank/statusline-cache.json'])
})

test('an empty HOME falls back to USERPROFILE', async ($, on) => {
  const paths = await pathsReadAfterPrompt($, on, { HOME: '', USERPROFILE: '/Users/ana-profile' })
  expect(paths).toEqual(['/Users/ana-profile/.clawd-tank/statusline-cache.json'])
})

test('HOME wins when both are set', async ($, on) => {
  const paths = await pathsReadAfterPrompt($, on, {
    HOME: '/Users/ana',
    USERPROFILE: '/Users/ana-profile',
  })
  expect(paths).toEqual(['/Users/ana/.clawd-tank/statusline-cache.json'])
})

test('with neither variable the cache is not read', async ($, on) => {
  expect(await pathsReadAfterPrompt($, on, {})).toEqual([])
})
