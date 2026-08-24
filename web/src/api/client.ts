import type { BrainstormApi } from '../types/contracts'
import { createSelectedApi, isDevelopmentSimulation } from '@brainstorm-api-adapter'

let api: BrainstormApi | undefined

export function getBrainstormApi(): BrainstormApi {
  if (!api) api = createSelectedApi()
  return api
}

export function isDevelopmentMockEnabled(): boolean {
  return isDevelopmentSimulation
}

export function resetBrainstormApi(): void {
  api = undefined
}
