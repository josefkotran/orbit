// What the "Mozek" pane draws from: the session's values the host keeps across a reload of the mod.

/** What the main loop is doing now. */
export type MozekPhase = 'idle' | 'waiting' | 'thinking' | 'writing' | 'tools'

/** One tool call of the current turn (main loop). */
export type MozekTool = {
  id: string
  name: string
  /** What it works on: a file name, the first line of a command, a pattern. */
  detail: string
  startedAt: number
  /** How long it ran, once it has. */
  ms?: number
  isError?: boolean
}

/** The last finished turn, in short. */
export type MozekTurn = {
  seconds: number
  steps: number
  tools: number
  tokensOut: number
  isAborted: boolean
}

/** A subagent that is running: what it does now and since when (clock ms). */
export type MozekAgent = { what: string; at: number }

export type MozekLive = {
  phase: MozekPhase
  /** When the running turn began (clock ms), 0 while idle. */
  turnStartedAt: number
  steps: number
  /** The tail of this turn's thinking, steps separated by a new line. */
  thinking: string
  /** The tail of what Claude writes. */
  answer: string
  tools: MozekTool[]
  agents: Record<string, MozekAgent>
  /** Output tokens of the main loop's recent requests, oldest first: the "brain wave". */
  wave: number[]
  last: MozekTurn | null
}

/** One square of the context grid: its category's theme colour and how full it is (0 = free). */
export type MozekSquare = { color: string; fill: number }

export type MozekCategory = { name: string; tokens: number; percent: number; color: string }

export type MozekLimit = { kind: string; percentUsed: number }

export type MozekContext = {
  percent: number | null
  tokens: number | null
  window: number
  limits: MozekLimit[]
  grid: MozekSquare[][]
  categories: MozekCategory[]
  model: string
}

declare module 'claude-code' {
  interface PluginState {
    'orbit-mozek': { live: MozekLive; context: MozekContext | null; tick: number }
  }
}
