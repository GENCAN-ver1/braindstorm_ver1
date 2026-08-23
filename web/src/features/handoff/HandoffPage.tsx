import { useEffect, useState } from 'react'
import type { HandoffContract } from '../../api/BrainstormApi'
import { getBrainstormApi } from '../../api/client'
import { useSession } from '../../state/SessionContext'

export function HandoffPage() {
  const { state } = useSession()
  const [handoff, setHandoff] = useState<HandoffContract | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      if (!state.sessionId) {
        setLoading(false)
        return
      }
      const result = await getBrainstormApi().getHandoff(state.sessionId)
      if (!cancelled) {
        setHandoff(result)
        setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [state.sessionId])

  if (loading) return <p>Loading…</p>

  if (!handoff) {
    return (
      <p role="status">
        The final handoff is only available after the Governor commits.
      </p>
    )
  }

  return (
    <section aria-labelledby="handoff-heading">
      <h1 id="handoff-heading">Final handoff</h1>

      <h2>Problem frame</h2>
      <pre>{handoff.problem_frame}</pre>

      <h2>Locked decisions</h2>
      <ul>
        {handoff.locked_decisions.map((decision) => (
          <li key={decision}>{decision}</li>
        ))}
      </ul>

      <h2>Non-goals</h2>
      <ul>
        {handoff.non_goals.map((goal) => (
          <li key={goal}>{goal}</li>
        ))}
      </ul>

      <h2>Acceptance criteria</h2>
      <ul>
        {handoff.acceptance_criteria.map((criterion) => (
          <li key={criterion}>{criterion}</li>
        ))}
      </ul>

      <h2>Evidence summary</h2>
      <ul>
        {handoff.evidence_summary.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>

      <h2>Recommended next action</h2>
      <p>{handoff.recommended_next_action}</p>
    </section>
  )
}
