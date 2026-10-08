// What the band above the prompt draws from: the task this session works on, as Orbit's tasks.json has it.

/** A note of the task: when (epoch seconds) and what. */
export type UkolNote = { at: number; text: string }

export type UkolTask = {
  id: string
  title: string
  folder: string
  /** Orbit's sections: active, planned, note, done. Orbit moves a task to done once its session is open, so
   * done here is no sign of the work being finished (that is isReported). */
  status: string
  context: string
  notes: UkolNote[]
  /** Orbit's data folder: tasks.json there, the inbox under tasks/inbox. */
  dataDir: string
  /** tasks.json doesn't have it (any more), or can't be read. */
  isMissing: boolean
}

declare module 'claude-code' {
  interface PluginState {
    'orbit-ukoly': {
      task: UkolTask | null
      /** The note field under the band is open. */
      isWriting: boolean
      /** The person hid the band (/ukol shows it again). */
      isHidden: boolean
      /** This session reported the task finished (Claude's task_done, or the band's Hotovo). */
      isReported: boolean
      /** A short line under the band after an action ("Poznámka je uložená"), cleared after a while. */
      flash: string
    }
  }
}
