import { describe, expect, it } from 'vitest'

import {
  FRAME_CANONICAL_FIELDS,
  IDEA_STAGE_TO_MODE,
  createAiSuggestion,
  validateFrameContinuation,
} from './mappings'
import type { FrameSchema } from './contracts'

const completeFrames = (): FrameSchema => ({
  target_user: { value: 'Independent product teams', status: 'KNOWN', source: 'user' },
  core_task: { value: 'Shape an idea', status: 'KNOWN', source: 'user' },
  desired_change: { value: 'Reach an evidence-backed decision', status: 'KNOWN', source: 'user' },
  hard_constraints: { value: ['No deployment'], status: 'KNOWN', source: 'user' },
  success_metrics: { value: ['A clear handoff'], status: 'KNOWN', source: 'user' },
  abandonment_criteria: { value: ['No viable path'], status: 'KNOWN', source: 'user' },
  non_goals: { value: ['Production hosting'], status: 'KNOWN', source: 'user' },
  validation_horizon: { value: 'One local session', status: 'KNOWN', source: 'user' },
})

describe('idea-stage mapping', () => {
  it('maps the four exact UI choices to the four Governor modes with no fifth mode', () => {
    expect(IDEA_STAGE_TO_MODE).toEqual({
      'I just have an idea': 'Shape',
      'I want to explore possibilities': 'Spark',
      'I already have a solution': 'Stress',
      'I need to make a decision': 'Decide',
    })
    expect(Object.keys(IDEA_STAGE_TO_MODE)).toHaveLength(4)
    expect(new Set(Object.values(IDEA_STAGE_TO_MODE))).toEqual(
      new Set(['Shape', 'Spark', 'Stress', 'Decide']),
    )
  })
})

describe('six-frame canonical mapping', () => {
  it('maps every wizard frame to only its frozen canonical fields', () => {
    expect(FRAME_CANONICAL_FIELDS).toEqual({
      'Who & Job': ['target_user', 'core_task'],
      'Desired Change': ['desired_change'],
      Constraints: ['hard_constraints'],
      Success: ['success_metrics'],
      'Failure Boundary': ['abandonment_criteria'],
      'Scope & Validation': ['non_goals', 'validation_horizon'],
    })
    expect(Object.keys(FRAME_CANONICAL_FIELDS)).toHaveLength(6)
  })

  it('blocks continuation when a required canonical field is UNKNOWN', () => {
    const frames = completeFrames()
    frames.core_task.status = 'UNKNOWN'

    expect(validateFrameContinuation(frames, 'Who & Job')).toEqual([
      {
        field: 'core_task',
        message: 'Core task is unknown. Provide a value and classify its evidence before continuing.',
      },
    ])
  })

  it('blocks continuation when a required canonical field is blank', () => {
    const frames = completeFrames()
    frames.validation_horizon.value = '   '

    expect(validateFrameContinuation(frames, 'Scope & Validation')).toEqual([
      {
        field: 'validation_horizon',
        message: 'Validation horizon is blank. Provide a value before continuing.',
      },
    ])
  })

  it('creates AI-originated values as ASSUMPTION rather than KNOWN', () => {
    expect(createAiSuggestion('Teams need a faster decision')).toEqual({
      value: 'Teams need a faster decision',
      status: 'ASSUMPTION',
      source: 'ai',
    })
  })
})
