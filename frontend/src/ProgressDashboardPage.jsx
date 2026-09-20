import { useEffect, useMemo, useState } from 'react'
import {
  Activity,
  BrainCircuit,
  CalendarCheck2,
  Flame,
  MessageSquare,
  RefreshCw,
  Target,
  Trophy,
} from 'lucide-react'
import { getProgressDashboard } from './api/notebooksApi'

function percent(value) {
  return Math.round(Number(value || 0) * 100)
}

export default function ProgressDashboardPage({ userId = 'default' }) {
  const [days, setDays] = useState(30)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      setData(await getProgressDashboard(userId, days))
    } catch (err) {
      setError(err?.message || 'Could not load Progress Dashboard.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [userId, days])

  const maxMessages = useMemo(
    () => Math.max(1, ...(data?.activity?.calendar || []).map((item) => Number(item.messages || 0))),
    [data],
  )

  const recentDays = (data?.activity?.calendar || []).slice(-14)

  return (
    <main className="main-content progress-dashboard-page">
      <div className="progress-header">
        <div>
          <div className="eyebrow">LEARNING TELEMETRY</div>
          <div className="progress-title-row">
            <div className="page-icon"><Activity size={22} /></div>
            <div>
              <h1>Progress Dashboard</h1>
              <p>See your study consistency, recall performance and actual Marklyf usage over time.</p>
            </div>
          </div>
        </div>
        <div className="progress-header-actions">
          <select value={days} onChange={(event) => setDays(Number(event.target.value))} aria-label="Progress window">
            <option value={7}>7 days</option>
            <option value={30}>30 days</option>
            <option value={90}>90 days</option>
          </select>
          <button className="chat-header-action" onClick={load} disabled={loading} title="Refresh" aria-label="Refresh">
            <RefreshCw size={16} className={loading ? 'spin' : ''} />
          </button>
        </div>
      </div>

      {error && <div className="planner-message">{error}</div>}

      {loading && !data ? (
        <div className="past-sessions-empty"><Activity size={26} className="spin" /><strong>Loading learning telemetry…</strong></div>
      ) : data && (
        <>
          <div className="progress-metric-grid">
            <Metric icon={<Flame size={17} />} label="Current streak" value={data.streak.current + ' days'} detail={'Longest: ' + data.streak.longest + ' days'} />
            <Metric icon={<Trophy size={17} />} label="Active days" value={data.streak.active_days} detail={'Across ' + data.window_days + ' days'} />
            <Metric icon={<MessageSquare size={17} />} label="Messages" value={data.activity.messages} detail={data.activity.sessions + ' sessions'} />
            <Metric icon={<BrainCircuit size={17} />} label="Socratic sessions" value={data.activity.socratic_sessions} detail={data.mastery.attempts + ' recall attempts'} />
          </div>

          <div className="progress-dashboard-grid">
            <section className="progress-card progress-activity-card">
              <div className="progress-card-header">
                <div>
                  <span className="eyebrow">CONSISTENCY</span>
                  <h2>Study activity</h2>
                </div>
                <CalendarCheck2 size={18} />
              </div>
              <div className="activity-bars">
                {recentDays.map((item) => {
                  const width = Math.max(4, Math.round((Number(item.messages || 0) / maxMessages) * 100))
                  return (
                    <div className="activity-day" key={item.date}>
                      <div className="activity-bar-track">
                        <div className="activity-bar-fill" style={{ width: width + '%' }} />
                      </div>
                      <span>{item.date.slice(5)}</span>
                      <small>{item.messages} msg</small>
                    </div>
                  )
                })}
                {!recentDays.length && <div className="past-sessions-empty">No activity recorded yet.</div>}
              </div>
            </section>

            <section className="progress-card">
              <div className="progress-card-header">
                <div>
                  <span className="eyebrow">RECALL</span>
                  <h2>Socratic mastery telemetry</h2>
                </div>
                <Target size={18} />
              </div>
              <div className="recall-score">
                <strong>{Number(data.mastery.average_score || 0).toFixed(1)}</strong>
                <span>/100 average mastery</span>
              </div>
              <div className="recall-progress">
                <div style={{ width: Math.max(0, Math.min(100, Number(data.mastery.average_score || 0))) + '%' }} />
              </div>
              <div className="recall-grid">
                <div><span>Accuracy</span><strong>{percent(data.mastery.accuracy)}%</strong></div>
                <div><span>Attempts</span><strong>{data.mastery.attempts}</strong></div>
                <div><span>Proficient topics</span><strong>{data.mastery.proficient_topics}</strong></div>
                <div><span>Mastered topics</span><strong>{data.mastery.mastered_topics}</strong></div>
              </div>
            </section>
          </div>

          <section className="progress-card progress-calendar-card">
            <div className="progress-card-header">
              <div>
                <span className="eyebrow">DAILY DETAIL</span>
                <h2>Activity ledger</h2>
              </div>
              <span className="progress-range">{data.window_start} → {data.window_end}</span>
            </div>
            <div className="progress-ledger">
              {(data.activity.calendar || []).slice().reverse().map((item) => (
                <div className="progress-ledger-row" key={item.date}>
                  <span>{item.date}</span>
                  <span>{item.sessions} sessions</span>
                  <span>{item.messages} messages</span>
                  <span>{item.date === data.window_end ? 'Today window' : ''}</span>
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </main>
  )
}

function Metric({ icon, label, value, detail }) {
  return (
    <div className="progress-metric">
      <div className="progress-metric-icon">{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  )
}
