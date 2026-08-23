import type { GovernorStatus, StageStatus } from '../../types/contracts'
import type { BadgeTone } from '../../components/StatusBadge'

export const STAGE_STATUS_LABELS: Record<StageStatus, string> = {
  pending: 'Pending',
  running: 'Running',
  complete: 'Complete',
  needs_input: 'Needs input',
  blocked: 'Blocked',
  skipped: 'Skipped',
  failed: 'Failed',
}

export const GOVERNOR_STATUS_LABELS: Record<GovernorStatus, string> = {
  NEEDS_INPUT: 'Needs input',
  RESEARCH_REQUIRED: 'Research required',
  EXPLORE: 'Explore',
  ITERATE: 'Iterate',
  PARK: 'Parked',
  COMMIT: 'Committed',
}

export const GOVERNOR_STATUS_TONE: Record<GovernorStatus, BadgeTone> = {
  NEEDS_INPUT: 'warning',
  RESEARCH_REQUIRED: 'warning',
  EXPLORE: 'info',
  ITERATE: 'warning',
  PARK: 'neutral',
  COMMIT: 'success',
}
