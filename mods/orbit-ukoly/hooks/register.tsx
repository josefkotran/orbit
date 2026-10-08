// Orbit's notes in the session that works on one of them. Orbit opens a task's session with ORBIT_TASK_ID and
// ORBIT_TASK_DATA (its data folder) in the environment; this mod then shows the task above the prompt with Poznámka
// and Hotovo, tells Claude about it, and gives Claude two tools: a note to the task, and the task done. Nothing writes
// Orbit's tasks.json but Orbit: what this session has to say goes as one small JSON file into <data>/tasks/inbox,
// which Orbit reads within a few seconds (tasks.read_inbox). /ukol lists the active tasks and ties a session to one.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { UkolNote, UkolTask } from '../types'

const task = atom({ plugin: 'orbit-ukoly', key: 'task' } as const, null as UkolTask | null)
const isWriting = atom({ plugin: 'orbit-ukoly', key: 'isWriting' } as const, false)
const isHidden = atom({ plugin: 'orbit-ukoly', key: 'isHidden' } as const, false)
const flash = atom({ plugin: 'orbit-ukoly', key: 'flash' } as const, '')
// tasks.json can't tell: Orbit puts a task in Hotovo as soon as its session is open
const isReported = atom({ plugin: 'orbit-ukoly', key: 'isReported' } as const, false)

const NOTE_TOOL = 'mcp__orbit-ukoly__task_note'
const DONE_TOOL = 'mcp__orbit-ukoly__task_done'
// the matchers as patterns: the engine's types list only tools connected at the last reload, and these two are
// registered later (only in a session with a task)
const NOTE_CALL = /^mcp__orbit-ukoly__task_note$/
const DONE_CALL = /^mcp__orbit-ukoly__task_done$/
const TEXT_MAX = 2000 // what Orbit keeps of one message (tasks.INBOX_TEXT_MAX)
const REFRESH_MS = 15_000 // tasks.json read again (the notebook may have changed the task)
const FLASH_MS = 5_000

type Raw = { id?: unknown; title?: unknown; folder?: unknown; status?: unknown; context?: unknown; notes?: unknown }

let refresher: { cancel: () => void } | null = null

const trimSlash = (dir: string): string => dir.replace(/[\\/]+$/, '')

/** The task as tasks.json in `dataDir` has it now; isMissing when it doesn't (or the file can't be read). */
async function load($: EngineInterface, id: string, dataDir: string): Promise<UkolTask> {
  const missing: UkolTask = { id, title: '', folder: '', status: '', context: '', notes: [], dataDir, isMissing: true }
  try {
    const data = JSON.parse(String(await $.fs.read(`${trimSlash(dataDir)}/tasks.json`))) as { tasks?: Raw[] }
    const raw = (data.tasks ?? []).find(t => t.id === id)
    if (!raw) return missing
    const notes = Array.isArray(raw.notes)
      ? raw.notes.filter((n): n is UkolNote => typeof n?.text === 'string').map(n => ({ at: Number(n.at) || 0, text: n.text }))
      : []
    return {
      id, dataDir, notes, isMissing: false,
      title: String(raw.title ?? ''), folder: String(raw.folder ?? ''),
      status: String(raw.status ?? ''), context: String(raw.context ?? ''),
    }
  } catch {
    return missing
  }
}

/** All the active tasks (for /ukol), in the notebook's order. */
async function activeTasks($: EngineInterface, dataDir: string): Promise<Raw[]> {
  const data = JSON.parse(String(await $.fs.read(`${trimSlash(dataDir)}/tasks.json`))) as { tasks?: Raw[] }
  return (data.tasks ?? []).filter(t => t.status === 'active' && typeof t.id === 'string')
}

/** Where Orbit keeps its data, for a session Orbit didn't open: what an Orbit-opened session told us before, then
 * the installed Orbit's folder, then a checkout in ~/orbit (git clone's default). */
async function findDataDir($: EngineInterface): Promise<string | null> {
  const candidates = [
    await $.env.get('ORBIT_TASK_DATA'),
    (await $.store.get('dataDir')) as string | undefined,
    await $.env.get('ORBIT_DATA_DIR'),
  ]
  const local = await $.env.get('LOCALAPPDATA')
  if (local) candidates.push(`${trimSlash(local)}/Orbit`)
  const home = await $.env.get('USERPROFILE')
  if (home) candidates.push(`${trimSlash(home)}/orbit`)
  for (const dir of candidates) {
    if (typeof dir === 'string' && dir && (await $.fs.exists(`${trimSlash(dir)}/tasks.json`))) return dir
  }
  return null
}

/** One message for Orbit: a file in its inbox, named so that they sort in the order written. */
async function send($: EngineInterface, t: UkolTask, action: 'note' | 'done', text: string, from: 'claude' | 'user'): Promise<void> {
  const now = await $.clock.now()
  const name = `${now}-${Math.random().toString(36).slice(2, 8)}.json`
  const message = { version: 1, task: t.id, action, text: text.slice(0, TEXT_MAX), from, at: now / 1000, session: await $.session.id() }
  await $.fs.write(`${trimSlash(t.dataDir)}/tasks/inbox/${name}`, JSON.stringify(message))
}

async function say($: EngineInterface, text: string): Promise<void> {
  await update($, flash, () => text)
  $.clock.after(FLASH_MS, () => void update($, flash, current => (current === text ? '' : current)))
}

/** Shown here and offered to Claude from now on; remembered for this session (a resumed one finds it again). */
async function attach($: EngineInterface, id: string, dataDir: string): Promise<UkolTask> {
  const loaded = await load($, id, dataDir)
  if ((await read($, task))?.id !== id) await update($, isReported, () => false) // another task: not finished yet
  await update($, task, () => loaded)
  await update($, isHidden, () => false)
  await $.store.set(`session:${await $.session.id()}`, { id, dataDir })
  await $.store.set('dataDir', dataDir)
  await $.tool.register({
    name: 'task_note',
    description:
      "Adds a note to the task this session works on, in the user's Orbit notes (the notebook). For a finding worth " +
      'keeping with the task: a decision, a blocker, where something is, what is left. Write it in Czech, one or two ' +
      'sentences. Not for progress chatter.',
    inputSchema: { type: 'object', properties: { text: { type: 'string', description: 'The note, in Czech.' } }, required: ['text'] },
    isDeferred: false,
  })
  await $.tool.register({
    name: 'task_done',
    description:
      "Marks the task this session works on as done in the user's Orbit notes: Orbit moves it to Hotovo and tells the " +
      'user. Call it once, only when the task is really finished, with a summary in Czech (one or two sentences: what ' +
      'was done, anything the user should check).',
    inputSchema: { type: 'object', properties: { summary: { type: 'string', description: 'What was done, in Czech.' } }, required: ['summary'] },
    isDeferred: false,
  })
  refresher?.cancel()
  refresher = $.clock.every(REFRESH_MS, () => void refresh($))
  return loaded
}

async function refresh($: EngineInterface): Promise<void> {
  const t = await read($, task)
  if (!t) return
  const fresh = await load($, t.id, t.dataDir)
  if (JSON.stringify(fresh) !== JSON.stringify(t)) await update($, task, () => fresh)
}

const notesWord = (n: number): string =>
  n === 0 ? 'bez poznámek' : n === 1 ? '1 poznámka' : n < 5 ? `${n} poznámky` : `${n} poznámek`

const folderName = (folder: string): string => trimSlash(folder).split(/[\\/]/).pop() ?? folder

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'ukol',
      description: 'Úkol z Poznámek Orbitu: ukáže ho nad promptem, nebo vypíše aktivní a relaci k jednomu připojí (/ukol 2)',
      argumentHint: '[číslo úkolu | odpojit]',
    })
    const id = await $.env.get('ORBIT_TASK_ID')
    const dataDir = await $.env.get('ORBIT_TASK_DATA')
    const saved = (await $.store.get(`session:${await $.session.id()}`)) as { id?: string; dataDir?: string } | undefined
    if (id && dataDir) await attach($, id, dataDir)
    else if (saved?.id && saved.dataDir) await attach($, saved.id, saved.dataDir)
    return next(e)
  })

  on('command.run', { command: 'ukol' }, async ($, e) => {
    const arg = e.args.trim()
    const t = await read($, task)
    if (arg === 'odpojit') {
      if (!t) return { text: 'Relace nepracuje na žádném úkolu z Poznámek.' }
      await update($, task, () => null)
      await $.store.delete(`session:${await $.session.id()}`)
      refresher?.cancel()
      refresher = null
      return { text: `Relace už není připojená k úkolu „${t.title}“.` }
    }
    if (!arg && t) {
      await update($, isHidden, () => false)
      return {}
    }
    const dataDir = t?.dataDir ?? (await findDataDir($))
    if (!dataDir) return { text: 'Poznámky Orbitu jsem nenašel. Otevři úkol z Poznámek Orbitu („Začít teď“) a pak to půjde i tady.' }
    const active = await activeTasks($, dataDir).catch(() => [] as Raw[])
    if (!arg) {
      if (!active.length) return { text: 'V Poznámkách Orbitu není žádný aktivní úkol.' }
      const lines = active.map((a, i) => `${i + 1}. ${String(a.title ?? '') || 'Bez názvu'}${a.folder ? ` (${folderName(String(a.folder))})` : ''}`)
      return { text: `Aktivní úkoly z Poznámek Orbitu:\n${lines.join('\n')}\n\nPřipojíš relaci k jednomu: /ukol <číslo>` }
    }
    const chosen = active[Number(arg) - 1]
    if (!/^\d+$/.test(arg) || !chosen) return { text: `Úkol ${arg} mezi aktivními není. Seznam ukáže /ukol.` }
    const attached = await attach($, String(chosen.id), dataDir)
    const notes = attached.notes.map(n => `- ${n.text}`).join('\n')
    return {
      text: `Relace pracuje na úkolu „${attached.title}“.`,
      context: [
        `This session now works on the user's Orbit task "${attached.title}".` +
          (attached.context ? `\nContext: ${attached.context}` : '') +
          (notes ? `\nNotes:\n${notes}` : ''),
      ],
    }
  })

  // Claude knows which task it works on and how to report back
  on('prompt.compose', async ($, e, next) => {
    const composed = await next(e)
    const t = await read($, task)
    if (!t || t.isMissing || (await read($, isReported))) return composed
    const text =
      `This session works on a task from the user's Orbit notes: "${t.title}"${t.folder ? ` (folder ${folderName(t.folder)})` : ''}. ` +
      `When the task is finished, call ${DONE_TOOL} with a short summary in Czech: Orbit then moves it to Hotovo (done) ` +
      `and tells the user. A finding worth keeping with the task (a decision, a blocker, where something is), write ` +
      `with ${NOTE_TOOL}, in Czech. Don't use them for anything else, and don't mark the task done before it really is.`
    return { sections: [...composed.sections, { id: 'orbit-ukoly:task', text, scope: 'session' }] }
  })

  on('tool.call', { tool: NOTE_CALL }, async ($, e) => {
    const t = await read($, task)
    const text = String((e as { text?: unknown }).text ?? '').trim()
    if (!t || t.isMissing) return { deny: 'Relace nepracuje na žádném úkolu z Poznámek Orbitu.' }
    if (!text) return { deny: 'Poznámka je prázdná.' }
    await send($, t, 'note', text, 'claude')
    await update($, task, cur => (cur ? { ...cur, notes: [...cur.notes, { at: Date.now() / 1000, text: `Claude: ${text}` }] } : cur))
    return { result: `Poznámka je uložená u úkolu „${t.title}“, Orbit ji do pár sekund zapíše do Poznámek.` }
  })

  on('tool.call', { tool: DONE_CALL }, async ($, e) => {
    const t = await read($, task)
    const summary = String((e as { summary?: unknown }).summary ?? '').trim()
    if (!t || t.isMissing) return { deny: 'Relace nepracuje na žádném úkolu z Poznámek Orbitu.' }
    await send($, t, 'done', summary, 'claude')
    await update($, isReported, () => true)
    await say($, 'Claude úkol dokončil, Orbit ti dá vědět.')
    return { result: `Úkol „${t.title}“ je hotový: Orbit ho zapíše do Poznámek a dá uživateli vědět.` }
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const t = await read($, task)
    if (!t || (e.props as { hasSurvey?: boolean }).hasSurvey || (await read($, isHidden))) return next(e)
    const elements = $.ui.resolve(e)
    const { Box, Button, Text } = elements
    const Input = 'Input' in elements ? elements.Input : null // (a phone has no text field)
    const writing = await read($, isWriting)
    const line = await read($, flash)
    const isDone = await read($, isReported)

    return (
      <Box flexDirection="column">
        <Box flexDirection="row" gap={1}>
          <Text color="claude">Úkol</Text>
          {t.isMissing ? (
            <Text dimColor wrap="truncate-end">
              v Poznámkách Orbitu už není
            </Text>
          ) : (
            <Box flexDirection="row" flexShrink={1} gap={1}>
              <Text bold wrap="truncate-end">
                {t.title || 'Bez názvu'}
              </Text>
              <Text dimColor wrap="truncate-end">
                {[t.folder && folderName(t.folder), notesWord(t.notes.length)].filter(Boolean).join(' · ')}
              </Text>
              {isDone && <Text color="success">✓ hotovo</Text>}
            </Box>
          )}
          <Box flexGrow={1} />
          {!t.isMissing && !writing && Input && (
            <Button key="note" label="Poznámka" hotkey="p" onPress={() => void update($, isWriting, () => true)} />
          )}
          {!t.isMissing && !isDone && (
            <Button
              key="done"
              label="Hotovo"
              hotkey="h"
              variant="primary"
              onPress={async () => {
                const cur = await read($, task)
                if (!cur) return
                await send($, cur, 'done', '', 'user')
                await update($, isReported, () => true)
                await say($, 'Úkol je hotový, Orbit to zapíše do Poznámek.')
              }}
            />
          )}
          <Button key="hide" label="Skrýt" plain dimColor onPress={() => void update($, isHidden, () => true)} />
        </Box>
        {writing && Input && (
          <Box flexDirection="row" gap={1}>
            <Input
              key="text"
              label="Poznámka: "
              placeholder="napiš a Enter"
              submitLabel="uložit"
              autoFocus
              onSubmit={async value => {
                const text = value.trim()
                const cur = await read($, task)
                await update($, isWriting, () => false)
                if (!text || !cur) return
                await send($, cur, 'note', text, 'user')
                await update($, task, c => (c ? { ...c, notes: [...c.notes, { at: Date.now() / 1000, text }] } : c))
                await say($, 'Poznámka je uložená, Orbit ji zapíše do Poznámek.')
              }}
            />
            <Button key="cancel" label="Zrušit" plain dimColor onPress={() => void update($, isWriting, () => false)} />
          </Box>
        )}
        {line && <Text dimColor>{line}</Text>}
      </Box>
    )
  })
}
