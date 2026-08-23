import type { FrameName, FrameSchema } from '../../types/contracts'

export type FrameFieldKind = 'textarea' | 'list'

export interface FrameFieldDefinition {
  key: keyof FrameSchema
  label: string
  kind: FrameFieldKind
  placeholder?: string
}

export interface FrameDefinition {
  name: FrameName
  slug: string
  route: string
  fields: FrameFieldDefinition[]
}

export const FRAME_DEFINITIONS: readonly FrameDefinition[] = [
  {
    name: 'Who & Job',
    slug: 'who-and-job',
    route: '/frames/who-and-job',
    fields: [
      {
        key: 'target_user',
        label: 'Target user',
        kind: 'textarea',
        placeholder: 'Who is this for?',
      },
      {
        key: 'core_task',
        label: 'Core task',
        kind: 'textarea',
        placeholder: 'What job are they trying to get done?',
      },
    ],
  },
  {
    name: 'Desired Change',
    slug: 'desired-change',
    route: '/frames/desired-change',
    fields: [
      {
        key: 'desired_change',
        label: 'Desired change',
        kind: 'textarea',
        placeholder: 'What should change for the user?',
      },
    ],
  },
  {
    name: 'Constraints',
    slug: 'constraints',
    route: '/frames/constraints',
    fields: [
      {
        key: 'hard_constraints',
        label: 'Hard constraints',
        kind: 'list',
        placeholder: 'A constraint that cannot be relaxed',
      },
    ],
  },
  {
    name: 'Success',
    slug: 'success',
    route: '/frames/success',
    fields: [
      {
        key: 'success_metrics',
        label: 'Success metrics',
        kind: 'list',
        placeholder: 'A measurable outcome',
      },
    ],
  },
  {
    name: 'Failure Boundary',
    slug: 'failure-boundary',
    route: '/frames/failure-boundary',
    fields: [
      {
        key: 'abandonment_criteria',
        label: 'Abandonment criteria',
        kind: 'list',
        placeholder: 'A condition under which to stop',
      },
    ],
  },
  {
    name: 'Scope & Validation',
    slug: 'scope-and-validation',
    route: '/frames/scope-and-validation',
    fields: [
      {
        key: 'non_goals',
        label: 'Non-goals',
        kind: 'list',
        placeholder: 'Something explicitly out of scope',
      },
      {
        key: 'validation_horizon',
        label: 'Validation horizon',
        kind: 'textarea',
        placeholder: 'How far does this validation reach?',
      },
    ],
  },
]

export const FRAME_BY_SLUG: Readonly<Record<string, FrameDefinition | undefined>> =
  Object.fromEntries(FRAME_DEFINITIONS.map((frame) => [frame.slug, frame]))

export const frameIndexBySlug = (slug: string): number =>
  FRAME_DEFINITIONS.findIndex((frame) => frame.slug === slug)
