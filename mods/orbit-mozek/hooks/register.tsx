// Orbit's "Mozek" (brain) pane for Claude Code, opened with /mozek: what the session is doing right now. The tail of
// Claude's thinking and of what it writes, the turn's tool calls with their times, running subagents, a "brain wave"
// of output tokens per request, and the context window as /context draws it (estimated locally, free), with limits.
// The limits also go to Orbit's panel: after each turn the engine hands over what the answers reported, and this mod
// leaves them in Orbit's data folder on this PC (reportLimits). Nothing is sent anywhere, nothing is asked for.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, SessionRateLimit } from 'claude-code'

import type { MozekContext, MozekLive, MozekPhase, MozekSquare, MozekTool } from '../types'

const PANE = 'mozek'
const IDLE: MozekLive = {
  phase: 'idle', turnStartedAt: 0, steps: 0, thinking: '', answer: '', tools: [], agents: {}, wave: [], last: null,
}
const live = atom({ plugin: 'orbit-mozek', key: 'live' } as const, IDLE)
const context = atom({ plugin: 'orbit-mozek', key: 'context' } as const, null as MozekContext | null)
const tick = atom({ plugin: 'orbit-mozek', key: 'tick' } as const, 0)

const THINKING_KEEP = 3000 // characters of thinking kept (the pane shows the end of it)
const ANSWER_KEEP = 800
const TOOLS_KEEP = 14
const WAVE_KEEP = 40
const FLUSH_MS = 120 // the stream's pieces reach the drawing at most this often
const CONTEXT_EVERY_MS = 2500 // the context grid is estimated again at most this often
const AGENT_STALE_MS = 10 * 60 * 1000

const PHASES: Record<MozekPhase, { icon: string; label: string; color: string }> = {
  idle: { icon: '○', label: 'v klidu', color: 'inactive' },
  waiting: { icon: '◌', label: 'čeká na model', color: 'subtle' },
  thinking: { icon: '✻', label: 'přemýšlí', color: 'claude' },
  writing: { icon: '✎', label: 'píše', color: 'success' },
  tools: { icon: '⚙', label: 'pracuje s nástroji', color: 'warning' },
}

// /context's category names, in Czech
const CATEGORY: Record<string, string> = {
  'System prompt': 'Systémový prompt',
  'System tools': 'Nástroje',
  'MCP tools': 'Nástroje MCP',
  'Custom agents': 'Vlastní agenti',
  'Memory files': 'Paměť (CLAUDE.md)',
  Skills: 'Dovednosti',
  'Slash commands': 'Příkazy',
  Messages: 'Zprávy',
  'Free space': 'Volné místo',
  'Autocompact buffer': 'Rezerva na kompaktování',
}

const LIMIT: Record<string, string> = { five_hour: '5 h', seven_day: 'týden' }
const SEEK_AGAIN_MS = 10 * 60 * 1000 // no Orbit data folder found: looked for again after this long

// Orbit's data folders (each has its config.json), found once per load: the folder Orbit was told to use, a task
// session's, the installed Orbit's, a checkout in ~/orbit. Every one found gets the limits: whichever Orbit runs
// reads its own.
let dataDirs: string[] | null = null
let soughtAt = 0

const trimSlash = (dir: string): string => dir.replace(/[\\/]+$/, '')

// The working copy the stream writes into; the host's copy (`live`) is what the pane draws and what survives a reload.
let cur: MozekLive | null = null
let flushPending = false
let ticker: { cancel: () => void } | null = null
let contextAt = 0

async function current($: EngineInterface): Promise<MozekLive> {
  if (!cur) cur = JSON.parse(JSON.stringify(await read($, live))) as MozekLive
  return cur
}

function flush($: EngineInterface): void {
  if (flushPending) return
  flushPending = true
  $.clock.after(FLUSH_MS, () => {
    flushPending = false
    const snapshot = cur
    if (snapshot) void update($, live, () => JSON.parse(JSON.stringify(snapshot)) as MozekLive)
  })
}

function startTicker($: EngineInterface): void {
  if (!ticker) ticker = $.clock.every(1000, () => void update($, tick, n => n + 1))
}

function stopTicker(): void {
  ticker?.cancel()
  ticker = null
}

/** What a tool call works on, in a few words. */
function detailOf(input: Record<string, unknown>): string {
  for (const field of ['file_path', 'notebook_path', 'path', 'command', 'pattern', 'description', 'url', 'query', 'skill']) {
    const value = input[field]
    if (typeof value !== 'string' || !value.trim()) continue
    if (field.endsWith('path')) return value.replace(/[\\/]+$/, '').split(/[\\/]/).pop() ?? value
    if (field === 'url') return value.replace(/^https?:\/\//, '').split('/')[0] ?? value
    return (value.trim().split('\n')[0] ?? '').slice(0, 80)
  }
  return ''
}

async function refreshContext($: EngineInterface, force = false): Promise<void> {
  const now = await $.clock.now()
  if (!force && now - contextAt < CONTEXT_EVERY_MS) return
  contextAt = now
  const usage = await $.session.usage({ breakdown: 'summary', columns: 80 })
  const b = usage.context.breakdown
  const value: MozekContext = {
    percent: usage.context.percent ?? b?.percentage ?? null,
    tokens: usage.context.tokens ?? b?.totalTokens ?? null,
    window: usage.context.window,
    limits: usage.rateLimits.map(r => ({ kind: r.kind, percentUsed: r.percentUsed })),
    grid: (b?.gridRows ?? []).map(row =>
      row.map((sq): MozekSquare => ({ color: sq.color, fill: sq.isFilled ? sq.squareFullness : 0 })),
    ),
    categories: (b?.categories ?? [])
      .filter(c => !c.isDeferred && c.tokens > 0)
      .map(c => ({
        name: CATEGORY[c.name] ?? c.name,
        tokens: c.tokens,
        percent: b && b.rawMaxTokens ? Math.round((c.tokens / b.rawMaxTokens) * 100) : 0,
        color: c.color,
      })),
    model: b?.model ?? (await $.session.model()),
  }
  await update($, context, () => value)
}

async function orbitDataDirs($: EngineInterface): Promise<string[]> {
  const now = await $.clock.now()
  if (dataDirs && (dataDirs.length || now - soughtAt < SEEK_AGAIN_MS)) return dataDirs
  soughtAt = now
  const candidates = [await $.env.get('ORBIT_DATA_DIR'), await $.env.get('ORBIT_TASK_DATA')]
  const local = await $.env.get('LOCALAPPDATA')
  if (local) candidates.push(`${trimSlash(local)}/Orbit`)
  const home = await $.env.get('USERPROFILE')
  if (home) candidates.push(`${trimSlash(home)}/orbit`)
  const found: string[] = []
  for (const dir of candidates) {
    if (!dir) continue
    const clean = trimSlash(dir)
    const key = clean.replace(/\\/g, '/').toLowerCase()
    if (found.some(f => f.replace(/\\/g, '/').toLowerCase() === key)) continue
    if (await $.fs.exists(`${clean}/config.json`).catch(() => false)) found.push(clean)
  }
  dataDirs = found
  return found
}

/** The limits the session's answers reported, for Orbit's panel: <data>/sessions/status/<session>.mod.json, read like
 * the files of Orbit's status line (app/claude_usage.py), resets_at as the engine gives it (ISO). */
async function reportLimits($: EngineInterface, limits: SessionRateLimit[]): Promise<void> {
  const windows: Record<string, { used_percentage: number; resets_at?: string }> = {}
  for (const limit of limits) {
    if (limit.kind !== 'five_hour' && limit.kind !== 'seven_day') continue
    windows[limit.kind] = { used_percentage: limit.percentUsed, ...(limit.resetsAt ? { resets_at: limit.resetsAt } : {}) }
  }
  if (!Object.keys(windows).length) return
  const session = await $.session.id()
  if (!/^[\w-]{1,128}$/.test(session)) return
  const record = JSON.stringify({ session_id: session, time: (await $.clock.now()) / 1000, source: 'orbit-mozek', rate_limits: windows })
  for (const dir of await orbitDataDirs($)) {
    await $.fs.write(`${dir}/sessions/status/${session}.mod.json`, record).catch(() => undefined)
  }
}

const tokens = (n: number): string =>
  n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1).replace('.', ',')} mil.` : n >= 1000 ? `${Math.round(n / 1000)}k` : `${n}`

const seconds = (ms: number): string => (ms < 10_000 ? `${(ms / 1000).toFixed(1).replace('.', ',')} s` : `${Math.round(ms / 1000)} s`)

const elapsed = (ms: number): string => {
  const s = Math.max(0, Math.round(ms / 1000))
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60} s`
}

/** The last `rows` rows of `text` at `width` columns, cut at a word, "…" in front when cut. */
function tail(text: string, width: number, rows: number): string {
  const room = Math.max(20, width) * rows
  const clean = text.replace(/\n{3,}/g, '\n\n').trim()
  if (clean.length <= room) return clean
  const cut = clean.slice(-room)
  const space = cut.search(/\s/)
  return '…' + (space >= 0 && space < 30 ? cut.slice(space + 1) : cut)
}

function wave(values: number[]): string {
  if (!values.length) return ''
  const bars = '▁▂▃▄▅▆▇█'
  const top = Math.max(...values, 1)
  return values.map(v => bars[Math.min(7, Math.floor((v / top) * 7.99))] ?? '▁').join('')
}

const square = (sq: MozekSquare): string => (sq.fill <= 0 ? '⛶' : sq.fill < 0.7 ? '⛀' : '⛁')

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'mozek',
      description: 'Mozek relace: o čem Claude přemýšlí, co dělají nástroje a jak je plný kontext',
    })
    return next(e)
  })

  // after each turn, and when a limit moved a whole point: what the answers reported, for Orbit (no request of its own)
  on('session.measure', async ($, e, next) => {
    const result = await next(e)
    if (e.rateLimits.length) await reportLimits($, e.rateLimits).catch(() => undefined)
    return result
  })

  on('command.run', { command: 'mozek' }, async $ => {
    await $.ui.open({ id: PANE, title: 'Mozek', columns: 60 })
    await refreshContext($, true).catch(() => undefined)
    return {}
  })

  on('turn.start', async ($, e, next) => {
    const L = await current($)
    Object.assign(L, { phase: 'waiting', turnStartedAt: await $.clock.now(), steps: 0, thinking: '', answer: '', tools: [] })
    flush($)
    startTicker($)
    return next(e)
  })

  on('turn.step', async function* ($, e, next) {
    const L = await current($)
    const agent = e.agentId
    const now = await $.clock.now()
    if (agent === undefined) {
      L.steps = e.index + 1
      L.phase = 'waiting'
      if (L.thinking && !L.thinking.endsWith('\n')) L.thinking += '\n'
      if (L.answer && !L.answer.endsWith('\n')) L.answer += '\n'
      flush($)
    }
    for await (const chunk of next(e)) {
      try {
        if (agent !== undefined) {
          const what = chunk.kind === 'thinking' ? 'přemýšlí' : chunk.kind === 'text' ? 'píše' : chunk.kind === 'tool' ? chunk.name : null
          if (what) L.agents[agent] = { what, at: now }
        } else if (chunk.kind === 'thinking') {
          L.phase = 'thinking'
          L.thinking = (L.thinking + chunk.text).slice(-THINKING_KEEP)
        } else if (chunk.kind === 'text') {
          L.phase = 'writing'
          L.answer = (L.answer + chunk.text).slice(-ANSWER_KEEP)
        } else if (chunk.kind === 'tool') {
          L.phase = 'tools'
        } else if (chunk.kind === 'stop' && chunk.usage) {
          L.wave = [...L.wave, chunk.usage.output_tokens].slice(-WAVE_KEEP)
        }
        flush($)
      } catch {
        // the pane is only a view: the stream goes on whatever happens here
      }
      yield chunk
    }
    if (agent === undefined) void refreshContext($).catch(() => undefined)
  })

  on('tool.call', async ($, e, next) => {
    const agent = (e as { agentId?: string }).agentId
    const L = await current($)
    const startedAt = await $.clock.now()
    const call: MozekTool = {
      id: e.tool_use_id ?? `${String(e.tool)}-${startedAt}`,
      name: String(e.tool).replace(/^mcp__([^_]+(?:_[^_]+)*)__/, '$1 · '),
      detail: detailOf(e as unknown as Record<string, unknown>),
      startedAt,
    }
    if (agent !== undefined) {
      L.agents[agent] = { what: `${call.name} ${call.detail}`.trim(), at: startedAt }
    } else {
      L.tools = [...L.tools, call].slice(-TOOLS_KEEP)
      L.phase = 'tools'
    }
    flush($)
    const ran = await next(e)
    if (agent === undefined) {
      const ended = await $.clock.now()
      const now = await current($)
      const done = now.tools.find(t => t.id === call.id)
      if (done) {
        done.ms = ended - startedAt
        done.isError = ran.deny !== undefined || ran.isError === true
        flush($)
      }
    }
    return ran
  })

  on('turn.complete', async ($, e, next) => {
    const L = await current($)
    if (e.agentId !== undefined) {
      delete L.agents[e.agentId]
      flush($)
      return next(e)
    }
    L.last = {
      seconds: Math.round(e.durationMs / 1000),
      steps: L.steps,
      tools: L.tools.length,
      tokensOut: e.usage?.output_tokens ?? 0,
      isAborted: e.isAborted,
    }
    L.phase = 'idle'
    L.turnStartedAt = 0
    flush($)
    stopTicker()
    void refreshContext($, true).catch(() => undefined)
    return next(e)
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const L = await read($, live)
    const C = await read($, context)
    await read($, tick) // a second passed: the running times move on
    const now = await $.clock.now()
    const width = Math.max(30, (e.props as { bodyColumns?: number }).bodyColumns ?? 56)
    const phase = PHASES[L.phase]
    const agents = Object.entries(L.agents).filter(([, a]) => now - a.at < AGENT_STALE_MS)

    const head =
      L.phase === 'idle'
        ? L.last
          ? `poslední tah ${elapsed(L.last.seconds * 1000)}, ${L.last.steps} ${L.last.steps === 1 ? 'krok' : 'kroků'}, ${L.last.tools} nástrojů${L.last.isAborted ? ', přerušen' : ''}`
          : 'zatím žádný tah'
        : `${elapsed(now - L.turnStartedAt)} · krok ${L.steps}`

    const barWidth = Math.max(10, width - 24)
    const filled = C?.percent != null ? Math.round((C.percent / 100) * barWidth) : 0
    const limits = (C?.limits ?? []).map(l => `${LIMIT[l.kind] ?? l.kind} ${Math.round(l.percentUsed)} %`).join(' · ')
    const gridCols = C?.grid[0]?.length ?? 0
    const spaced = width >= gridCols * 2 + 32
    const legendBeside = width >= (spaced ? gridCols * 2 : gridCols) + 30

    const grid = (
      <Box flexDirection="column" flexShrink={0}>
        {(C?.grid ?? []).map(row => (
          <Box flexDirection="row">
            {row.map(sq => (
              <Text color={sq.fill > 0 ? sq.color : 'inactive'}>{square(sq) + (spaced ? ' ' : '')}</Text>
            ))}
          </Box>
        ))}
      </Box>
    )
    const legend = (
      <Box flexDirection="column" marginLeft={legendBeside ? 2 : 0} marginTop={legendBeside ? 0 : 1}>
        {(C?.categories ?? []).map(c => (
          <Box flexDirection="row">
            <Text color={c.color}>⛁ </Text>
            <Text wrap="truncate-end">{c.name}</Text>
            <Text dimColor> {tokens(c.tokens)} ({c.percent} %)</Text>
          </Box>
        ))}
      </Box>
    )

    return (
      <Box flexDirection="column">
        <Box flexDirection="row">
          <Text bold color={phase.color}>
            {phase.icon} {phase.label}
          </Text>
          <Text dimColor> · {head}</Text>
        </Box>

        {C && (
          <Box flexDirection="column" marginTop={1}>
            <Box flexDirection="row">
              <Text>Kontext </Text>
              <Text color={(C.percent ?? 0) >= 80 ? 'warning' : 'claude'}>{'█'.repeat(filled)}</Text>
              <Text dimColor>{'░'.repeat(Math.max(0, barWidth - filled))}</Text>
              <Text> {C.percent ?? '?'} %</Text>
            </Box>
            <Text dimColor wrap="truncate-end">
              {C.tokens != null ? `${tokens(C.tokens)} z ${tokens(C.window)}` : `okno ${tokens(C.window)}`}
              {limits ? ` · ${limits}` : ''} · {C.model}
            </Text>
          </Box>
        )}

        {L.wave.length > 1 && (
          <Box flexDirection="row" marginTop={1}>
            <Text dimColor>Aktivita </Text>
            <Text color="claude">{wave(L.wave.slice(-(width - 10)))}</Text>
          </Box>
        )}

        <Box flexDirection="column" marginTop={1}>
          <Text bold>Myšlenky</Text>
          {L.thinking.trim() ? (
            <Text dimColor italic wrap="wrap">
              {tail(L.thinking, width, 7)}
            </Text>
          ) : (
            <Text dimColor>{L.phase === 'idle' && !L.last ? 'Pošli Claudovi zprávu a uvidíš, jak přemýšlí.' : '(v tomhle tahu nic, nebo jsou skryté)'}</Text>
          )}
        </Box>

        {L.answer.trim() && L.phase !== 'idle' && (
          <Box flexDirection="column" marginTop={1}>
            <Text bold>Píše</Text>
            <Text wrap="wrap">{tail(L.answer, width, 3)}</Text>
          </Box>
        )}

        {L.tools.length > 0 && (
          <Box flexDirection="column" marginTop={1}>
            <Text bold>Nástroje</Text>
            {L.tools.slice(-8).map(t => (
              <Box flexDirection="row">
                <Text color={t.ms === undefined ? 'warning' : t.isError ? 'error' : 'success'}>
                  {t.ms === undefined ? '▸ ' : t.isError ? '✗ ' : '✓ '}
                </Text>
                <Text bold>{t.name} </Text>
                <Box flexGrow={1} flexShrink={1}>
                  <Text dimColor wrap="truncate-end">
                    {t.detail}
                  </Text>
                </Box>
                <Text dimColor> {seconds(t.ms ?? now - t.startedAt)}</Text>
              </Box>
            ))}
          </Box>
        )}

        {agents.length > 0 && (
          <Box flexDirection="column" marginTop={1}>
            <Text bold>Podagenti ({agents.length})</Text>
            {agents.slice(-4).map(([, a]) => (
              <Text dimColor wrap="truncate-end">
                ⧉ {a.what}
              </Text>
            ))}
          </Box>
        )}

        {(C?.grid.length ?? 0) > 0 && (
          <Box flexDirection="column" marginTop={1}>
            <Text bold>Kontext podle kategorií</Text>
            <Box flexDirection={legendBeside ? 'row' : 'column'}>
              {grid}
              {legend}
            </Box>
          </Box>
        )}
      </Box>
    )
  })
}
