import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import type {
  FrameSchema,
  FrameValue,
  FrontendSessionState,
  IdeaStageChoice,
} from '../types/contracts'
import {
  persistFrontendSessionState,
  restoreFrontendSessionState,
} from './sessionPersistence'

const emptyStringValue = (): FrameValue<string> => ({
  value: '',
  status: 'UNKNOWN',
  source: 'user',
})

const emptyListValue = (): FrameValue<string[]> => ({
  value: [],
  status: 'UNKNOWN',
  source: 'user',
})

const createEmptyFrames = (): FrameSchema => ({
  target_user: emptyStringValue(),
  core_task: emptyStringValue(),
  desired_change: emptyStringValue(),
  hard_constraints: emptyListValue(),
  success_metrics: emptyListValue(),
  abandonment_criteria: emptyListValue(),
  non_goals: emptyListValue(),
  validation_horizon: emptyStringValue(),
})

const createInitialState = (): FrontendSessionState => ({
  route: '/intake',
  idea: '',
  currentFrame: 0,
  frames: createEmptyFrames(),
})

const isBlankValue = (value: string | string[]): boolean =>
  typeof value === 'string'
    ? value.trim().length === 0
    : value.length === 0 || value.every((item) => item.trim().length === 0)

interface SessionContextValue {
  state: FrontendSessionState
  setIdea: (idea: string) => void
  selectIdeaStage: (stage: IdeaStageChoice) => void
  setFrameValue: (field: keyof FrameSchema, value: string | string[]) => void
  setRoute: (route: string) => void
  setCurrentFrame: (index: number) => void
  setSession: (id: string, revision: number) => void
}

const SessionContext = createContext<SessionContextValue | null>(null)

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<FrontendSessionState>(() => {
    if (typeof window !== 'undefined') {
      const restored = restoreFrontendSessionState(window.sessionStorage)
      if (restored) return restored
    }
    return createInitialState()
  })

  useEffect(() => {
    if (typeof window !== 'undefined') {
      persistFrontendSessionState(window.sessionStorage, state)
    }
  }, [state])

  const setIdea = useCallback((idea: string) => {
    setState((prev) => ({ ...prev, idea }))
  }, [])

  const selectIdeaStage = useCallback((stage: IdeaStageChoice) => {
    setState((prev) => ({ ...prev, selectedIdeaStage: stage }))
  }, [])

  const setFrameValue = useCallback((field: keyof FrameSchema, value: string | string[]) => {
    setState((prev) => ({
      ...prev,
      frames: {
        ...prev.frames,
        [field]: {
          value,
          status: isBlankValue(value) ? 'UNKNOWN' : 'KNOWN',
          source: 'user',
        },
      } as FrameSchema,
    }))
  }, [])

  const setRoute = useCallback((route: string) => {
    setState((prev) => ({ ...prev, route }))
  }, [])

  const setCurrentFrame = useCallback((index: number) => {
    setState((prev) => ({ ...prev, currentFrame: index }))
  }, [])

  const setSession = useCallback((id: string, revision: number) => {
    setState((prev) => ({ ...prev, sessionId: id, revision }))
  }, [])

  const value = useMemo(
    () => ({
      state,
      setIdea,
      selectIdeaStage,
      setFrameValue,
      setRoute,
      setCurrentFrame,
      setSession,
    }),
    [state, setIdea, selectIdeaStage, setFrameValue, setRoute, setCurrentFrame, setSession],
  )

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext)
  if (!context) throw new Error('useSession must be used within a SessionProvider')
  return context
}
