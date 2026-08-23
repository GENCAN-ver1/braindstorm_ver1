import type {
  CapabilityProvider,
  CapabilityRequest,
  EphemeralProviderSecret,
  MissingInputSubmission,
} from './contracts'

const provider = (name: string): CapabilityProvider => ({
  name,
  baseUrl: 'https://provider.example.test',
  model: 'test-model',
  apiKey: 'fake-key' as EphemeralProviderSecret,
})

export const validStringInput: MissingInputSubmission = {
  field: 'core_task',
  value: 'Shape an idea',
  status: 'KNOWN',
}

export const validListInput: MissingInputSubmission = {
  field: 'non_goals',
  value: ['Deploying'],
  status: 'ASSUMPTION',
}

// @ts-expect-error core_task requires a string value
export const invalidStringInput: MissingInputSubmission = {
  field: 'core_task',
  value: ['Shape an idea'],
  status: 'KNOWN',
}

// @ts-expect-error non_goals requires a string-array value
export const invalidListInput: MissingInputSubmission = {
  field: 'non_goals',
  value: 'Deploying',
  status: 'KNOWN',
}

export const validSkip: CapabilityRequest = {
  capability: 'council',
  outcome: 'skip',
  authorized: false,
}

export const validCouncil: CapabilityRequest = {
  capability: 'council',
  outcome: 'enable',
  authorized: true,
  providers: [provider('one'), provider('two')],
}

export const validResearch: CapabilityRequest = {
  capability: 'research',
  outcome: 'enable',
  authorized: true,
  providers: [provider('one')],
}

// @ts-expect-error skip cannot be authorized
export const invalidAuthorizedSkip: CapabilityRequest = {
  capability: 'research',
  outcome: 'skip',
  authorized: true,
}

export const invalidSkipProviders: CapabilityRequest = {
  capability: 'evaluator',
  outcome: 'skip',
  authorized: false,
  // @ts-expect-error skip cannot carry providers
  providers: [provider('one')],
}

// @ts-expect-error enabled capability must be authorized
export const invalidUnauthorizedEnable: CapabilityRequest = {
  capability: 'research',
  outcome: 'enable',
  authorized: false,
  providers: [provider('one')],
}

// @ts-expect-error Council requires at least two providers
export const invalidSingleProviderCouncil: CapabilityRequest = {
  capability: 'council',
  outcome: 'enable',
  authorized: true,
  providers: [provider('one')],
}

export const invalidEmptyResearch: CapabilityRequest = {
  capability: 'research',
  outcome: 'enable',
  authorized: true,
  // @ts-expect-error Research requires at least one provider
  providers: [],
}
