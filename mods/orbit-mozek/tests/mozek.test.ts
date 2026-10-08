// A turn as the engine raises it (start, a streamed request with thinking, text and a tool, the tool's call, the
// end) and the "Mozek" pane drawn on the terminal and the desktop: what it shows.
import { expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

/** What the engine itself answers beneath the plugin, as plainly as the plugin needs it. */
function engine(on: On) {
  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('command.register', () => ({ value: {} }) as never)
  on('turn.start', ($, e) => ({ turnId: e.turnId }))
  on('turn.complete', ($, e) => ({ text: e.answer }))
}

const pane = {
  component: 'Pane',
  requestId: 'mozek',
  props: { title: 'Mozek', isFocused: false, bodyColumns: 60, placement: 'dock', scroll: { offset: 0, bodyRows: 60 }, view: {} },
} as const

const square = (color: string, isFilled: boolean) => ({
  color, isFilled, categoryName: isFilled ? 'Messages' : 'Free space', tokens: 50000, percentage: 25, squareFullness: isFilled ? 1 : 0,
})

test('a turn shows in the pane: thinking, the tool and its time, the context', async ($, on) => {
  const clock = mock.clock(on, { now: 1_000 })
  engine(on)
  on('session.model', () => ({ value: 'claude-opus-5-5' }))
  on('session.usage', () => ({ value: {
    startedAt: 0,
    context: {
      window: 200_000, tokens: 50_000, percent: 25,
      breakdown: {
        categories: [
          { name: 'Messages', tokens: 50_000, color: 'claude', isDeferred: false, kind: 'used' as const },
          { name: 'Free space', tokens: 150_000, color: 'inactive', isDeferred: false, kind: 'free' as const },
        ],
        totalTokens: 50_000, maxTokens: 200_000, rawMaxTokens: 200_000, autocompactSource: 'model' as never,
        percentage: 25, gridRows: [[square('claude', true), square('inactive', false)]], model: 'claude-opus-5-5',
        memoryFiles: [], mcpTools: [], agents: [], isAutoCompactEnabled: true, apiUsage: null,
      },
    },
    rateLimits: [{ kind: 'five_hour', percentUsed: 23 }],
  } }))
  on('turn.step', async function* () {
    yield { kind: 'thinking' as const, index: 0, text: 'Nejdřív si přečtu ceník, pak ' }
    yield { kind: 'thinking' as const, index: 0, text: 'porovnám ceny.' }
    yield { kind: 'tool' as const, index: 1, id: 'tu1', name: 'Read' }
    yield { kind: 'stop' as const, stopReason: 'tool_use' as const, usage: { input_tokens: 10, output_tokens: 420, cache_creation_input_tokens: 0, cache_read_input_tokens: 0, model: 'opus' } }
    return { turnId: 't1', index: 0, answer: '', toolUses: [], stopReason: 'tool_use' as const, usage: null }
  })
  on('tool.call', async () => {
    await clock.sleep(1_500)
    return { result: 'obsah' }
  })

  await $.session.start({ cwd: 'C:/projekt', surface: 'terminal', isInteractive: true })
  await $.turn.start({ text: 'Porovnej ceník', turnId: 't1' })
  for await (const _ of $.turn.step({ turnId: 't1', index: 0, model: 'claude-opus-5-5', messageCount: 1 })) {
    // the plugin sees each piece on its way
  }
  const call = $.tool.call({ tool: 'Read', file_path: 'C:/projekt/data/cenik.md', tool_use_id: 'tu1' })
  await clock.advance(1_500)
  await call
  await $.turn.complete({ answer: 'Hotovo.', durationMs: 4_000, isAborted: false, turnId: 't1', reason: 'end_turn' as never })
  await clock.advance(3_000)

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ plugin: 'orbit-mozek', surface, ...pane })
    expect(await ui.find({ type: 'Text', text: /porovnám ceny/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /cenik\.md/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /1,5 s/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /poslední tah 4 s/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /5 h 23 %/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /Zprávy/ })).toBeDefined()
    await ui.unmount()
  }
})

test('/mozek opens the pane and writes nothing into the conversation', async ($, on) => {
  mock.clock(on)
  engine(on)
  const opened: string[] = []
  on('ui.open', ($, e) => {
    opened.push(e.id)
    return { value: {} } as never
  })
  await $.session.start({ cwd: 'C:/projekt', surface: 'terminal', isInteractive: true })
  // origin and presentation: the kit stamps them as the engine does
  const ran = await $.command.run({ command: 'mozek', args: '' } as never)
  expect(ran.text).toBeUndefined()
  expect(opened).toEqual(['mozek'])
})
