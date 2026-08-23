import type { BrainstormApiError, BrainstormApiErrorCode } from '../types/contracts'

export const isBrainstormApiError = (value: unknown): value is BrainstormApiError =>
  typeof value === 'object' &&
  value !== null &&
  'code' in value &&
  typeof (value as { code: unknown }).code === 'string' &&
  'message' in value &&
  typeof (value as { message: unknown }).message === 'string'

export const apiError = (
  code: BrainstormApiErrorCode,
  message: string,
  options: { field?: string; retryable?: boolean } = {},
): BrainstormApiError => ({
  code,
  message,
  field: options.field,
  retryable: options.retryable ?? false,
})
