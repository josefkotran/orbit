// The session Orbit opened for a task: the band shows it, Claude's tools and the band's buttons leave messages in
// Orbit's inbox (and nothing else is written), Claude is told about the task. And /ukol in a session of its own.
import { expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

const DATA = 'C:/Users/pepa/orbit'
/** The engine hands paths on in the platform's spelling (backslashes on Windows). */
const norm = (path: string): string => path.replace(/\\/g, '/')
const TASKS = {
  version: 1,
  tasks: [
    { id: 'aaa111', title: 'Web', folder: 'C:/proj/web', status: 'planned', context: '', notes: [] },
    // in Hotovo already: Orbit moves a task there as soon as it opens its session
    { id: 'bbb222', title: 'Faktury za září', folder: 'C:/proj/faktury', status: 'done', context: 'Poslat účetní.',
      notes: [{ at: 1, text: 'Pozor na DPH' }, { at: 2, text: 'Do pátku' }] },
    { id: 'ccc333', title: 'Ceník', folder: 'C:/proj/eshop', status: 'active', context: '', notes: [] },
  ],
}

type Written = { path: string; text: string }

const COMPOSE = { model: 'claude-opus-5-5', promptModel: 'claude-opus-5-5', surfaces: ['terminal' as const], tools: [], outputStyle: null, traits: [] }

/** What the engine and the disk answer beneath the plugin; returns what it wrote. */
function world(on: On, env: Record<string, string>): Written[] {
  const written: Written[] = []
  mock.clock(on, { now: 1_760_000_000_000 })
  mock.store(on)
  mock.env(on, env)
  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('session.id', () => ({ value: 'sess-1' }))
  on('command.register', () => ({ value: {} }) as never)
  on('tool.register', ($, e) => ({ value: { tool: `mcp__orbit-ukoly__${e.name}` } }) as never)
  on('fs.read', ($, e) =>
    norm(e.path) === `${DATA}/tasks.json` ? { value: JSON.stringify(TASKS) } : { deny: `no file ${e.path}` },
  )
  on('fs.exists', ($, e) => ({ value: norm(e.path) === `${DATA}/tasks.json` }))
  on('fs.write', ($, e) => {
    written.push({ path: norm(e.path), text: e.text })
    return { value: undefined }
  })
  on('prompt.compose', () => ({ sections: [{ id: 'intro', text: 'You are Claude Code.', scope: 'shared' as const }] }))
  // the engine's own band (nothing of the plugin's): an empty keyed Box
  on('ui.render', { component: 'AbovePrompt' }, ($, e) => $.ui.resolve(e).Box({ key: 'engine' }))
  return written
}

const band = {
  component: 'AbovePrompt',
  props: { hasSurvey: false, isWorking: false, maxRows: 10, bodyColumns: 110, scroll: { offset: 0, bodyRows: 10 }, view: {} },
} as const

const messages = (written: Written[]) =>
  written.filter(w => w.path.startsWith(`${DATA}/tasks/inbox/`)).map(w => JSON.parse(w.text) as Record<string, unknown>)

test('a session Orbit opened for a task shows it and reports back through the inbox', async ($, on) => {
  const written = world(on, { ORBIT_TASK_ID: 'bbb222', ORBIT_TASK_DATA: DATA })
  await $.session.start({ cwd: 'C:/proj/faktury', surface: 'terminal', isInteractive: true })

  const prompt = await $.prompt.compose(COMPOSE)
  const section = prompt.sections.find(s => s.id === 'orbit-ukoly:task')
  expect(section?.text).toContain('"Faktury za září"')
  expect(section?.scope).toBe('session')

  const ui = await $.ui.mount({ plugin: 'orbit-ukoly', surface: 'terminal', ...band })
  expect(await ui.find({ type: 'Text', text: 'Faktury za září' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /faktury · 2 poznámky/ })).toBeDefined()

  await $.tool.call({ tool: 'mcp__orbit-ukoly__task_note', text: 'Září má 48 faktur.' } as never)
  await ui.press({ key: 'note' })
  await ui.input({ key: 'text', text: 'Volat Petrovi' })
  const done = await $.tool.call({ tool: 'mcp__orbit-ukoly__task_done', summary: 'Odesláno účetní.' } as never)
  expect(String(done.result)).toContain('Faktury za září')

  expect(messages(written).map(m => [m.task, m.action, m.text, m.from])).toEqual([
    ['bbb222', 'note', 'Září má 48 faktur.', 'claude'],
    ['bbb222', 'note', 'Volat Petrovi', 'user'],
    ['bbb222', 'done', 'Odesláno účetní.', 'claude'],
  ])
  expect(written.every(w => w.path.startsWith(`${DATA}/tasks/inbox/`))).toBe(true) // tasks.json stays Orbit's
  expect(await ui.find({ type: 'Text', text: /✓ hotovo/ })).toBeDefined()
  expect(await ui.find({ key: 'done' })).toBeUndefined() // done: no second "Hotovo"
  await ui.unmount()

  // done: Claude isn't told to work on it any more
  const after = await $.prompt.compose(COMPOSE)
  expect(after.sections.find(s => s.id === 'orbit-ukoly:task')).toBeUndefined()
})

test('a session of its own: no band, /ukol lists the active tasks and ties the session to one', async ($, on) => {
  const written = world(on, { USERPROFILE: 'C:/Users/pepa' })
  await $.session.start({ cwd: 'C:/proj', surface: 'terminal', isInteractive: true })
  const ui = await $.ui.mount({ plugin: 'orbit-ukoly', surface: 'terminal', ...band })
  expect(await ui.find({ type: 'Text', text: /Úkol/ })).toBeUndefined()
  await ui.unmount()

  const list = await $.command.run({ command: 'ukol', args: '' } as never)
  expect(list.text).toContain('1. Ceník (eshop)')
  expect(list.text).not.toContain('Web') // planned
  expect(list.text).not.toContain('Faktury') // its session runs: Hotovo

  const tied = await $.command.run({ command: 'ukol', args: '1' } as never)
  expect(tied.text).toContain('„Ceník“')
  const prompt = await $.prompt.compose(COMPOSE)
  expect(prompt.sections.find(s => s.id === 'orbit-ukoly:task')?.text).toContain('"Ceník"')

  const wrong = await $.command.run({ command: 'ukol', args: '9' } as never)
  expect(wrong.text).toContain('není')
  const off = await $.command.run({ command: 'ukol', args: 'odpojit' } as never)
  expect(off.text).toContain('Ceník')
  expect(messages(written)).toEqual([])
})

test('Claude\'s tools refuse in a session without a task', async ($, on) => {
  world(on, {})
  await $.session.start({ cwd: 'C:/proj', surface: 'terminal', isInteractive: true })
  const ran = await $.tool.call({ tool: 'mcp__orbit-ukoly__task_note', text: 'x' } as never)
  expect(ran.deny).toContain('nepracuje')
})
