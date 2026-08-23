import type { ReactNode } from 'react'

export type BadgeTone = 'neutral' | 'info' | 'warning' | 'danger' | 'success'

export interface StatusBadgeProps {
  tone?: BadgeTone
  children: ReactNode
}

export function StatusBadge({ tone = 'neutral', children }: StatusBadgeProps) {
  return <span className={`status-badge status-badge--${tone}`}>{children}</span>
}
