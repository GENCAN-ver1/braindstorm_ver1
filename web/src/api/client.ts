import type { BrainstormApi } from '../types/contracts'
import { createDevelopmentMock } from './developmentMock'

let api: BrainstormApi | undefined

export function getBrainstormApi(): BrainstormApi {
  if (!api) api = createDevelopmentMock()
  return api
}

export function resetBrainstormApi(): void {
  api = undefined
}
