import type { Tone } from '../components/ui'

/**
 * How a class lifecycle state is shown to a person.
 *
 * The domain keeps the canonical vocabulary (`ACTIVE`, `COMPLETED`, ...), but the
 * teacher and the student should read "Live" and "Ended". `COMPLETED` is
 * deliberately called **Ended**: the session is closed and its lesson is locked
 * until a teacher reopens it.
 */
export const STATE_TONE: Record<string, Tone> = {
  SCHEDULED: 'info',
  PREPARING: 'warn',
  ACTIVE: 'good',
  DEGRADED: 'warn',
  RECOVERING: 'warn',
  ENDING: 'warn',
  COMPLETED: 'neutral',
  FAILED: 'bad',
}

export function stateLabel(state: string): string {
  switch (state) {
    case 'SCHEDULED':
      return 'Scheduled'
    case 'PREPARING':
      return 'Starting'
    case 'ACTIVE':
      return 'Live'
    case 'DEGRADED':
      return 'Live (degraded)'
    case 'RECOVERING':
      return 'Recovering'
    case 'ENDING':
      return 'Ending'
    case 'COMPLETED':
      return 'Ended'
    case 'FAILED':
      return 'Failed'
    default:
      return state
  }
}
