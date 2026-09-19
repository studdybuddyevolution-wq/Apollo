import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle2, Clock3, Plus, RefreshCw } from 'lucide-react'
import {
  createPlannerCourse,
  createPlannerTopic,
  getPlannerDashboard,
  setDailyStudyHours,
  updatePlannerTopic,
} from './api/plannerApi'

function formatTarget(value) {
  if (!value) return 'No deadline set'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

export default function PlannerPage({ userId = 'default', mode = 'planner' }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [dailyHours, setDailyHours] = useState(2)
  const [course, setCourse] = useState({ code: '', title: '', deadline_at: '', priority: 3 })
  const [topic, setTopic] = useState({ course_id: '', title: '', estimated_hours: 1, lecture_at: '' })

  const load = async () => {
    setLoading(true)
    try {
      const result = await getPlannerDashboard(userId)
      setData(result)
      setDailyHours(result.daily_hours || 2)
      setTopic((current) => ({ ...current, course_id: current.course_id || result.courses?.[0]?.id || '' }))
      setMessage('')
    } catch (error) {
      setMessage(error?.message || 'Planner unavailable. Configure DATABASE_URL to enable persistence.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [userId])

  const riskCount = useMemo(
    () => (data?.fall_behind || []).filter((item) => item.severity !== 'ok').length,
    [data],
  )

  const saveHours = async () => {
    try {
      await setDailyStudyHours(dailyHours, userId)
      await load()
      setMessage('Daily capacity updated.')
    } catch (error) {
      setMessage(error?.message || 'Could not update study capacity.')
    }
  }

  const addCourse = async (event) => {
    event.preventDefault()
    try {
      await createPlannerCourse(course, userId)
      setCourse({ code: '', title: '', deadline_at: '', priority: 3 })
      await load()
      setMessage('Course added.')
    } catch (error) {
      setMessage(error?.message || 'Could not create course.')
    }
  }

  const addTopic = async (event) => {
    event.preventDefault()
    try {
      await createPlannerTopic(topic, userId)
      setTopic((current) => ({ ...current, title: '', estimated_hours: 1, lecture_at: '' }))
      await load()
      setMessage('Topic added.')
    } catch (error) {
      setMessage(error?.message || 'Could not create topic.')
    }
  }

  const mark = async (topicId, status) => {
    try {
      await updatePlannerTopic(topicId, status, userId)
      await load()
    } catch (error) {
      setMessage(error?.message || 'Could not update topic.')
    }
  }

  if (loading && !data) {
    return <main className="main-content placeholder-page"><div className="page-heading"><div className="page-icon"><Clock3 size={22}/></div><div><div className="eyebrow">STUDY SYSTEM</div><h1>Loading planner…</h1><p>Reading courses, topics and deadlines.</p></div></div></main>
  }

  return (
    <main className="main-content planner-page">
      <div className="page-heading">
        <div className="page-icon"><Clock3 size={22}/></div>
        <div>
          <div className="eyebrow">{mode === 'progress' ? 'PROGRESS DASHBOARD' : 'STUDY PLANNER'}</div>
          <h1>{mode === 'progress' ? 'See how your semester is moving' : 'Plan around what can actually fit'}</h1>
          <p>{riskCount ? `${riskCount} course${riskCount === 1 ? '' : 's'} need catch-up attention.` : 'No active fall-behind warnings right now.'}</p>
        </div>
        <button className="topbar-tool" onClick={load} title="Refresh planner"><RefreshCw size={15}/> Refresh</button>
      </div>

      {message && <div className="planner-message">{message}</div>}

      <div className="planner-stats">
        <div className="planner-stat"><span>Topics complete</span><strong>{data?.progress?.topics_completed || 0}/{data?.progress?.topics_total || 0}</strong></div>
        <div className="planner-stat"><span>Completion</span><strong>{Math.round((data?.progress?.completion_ratio || 0) * 100)}%</strong></div>
        <div className="planner-stat"><span>Hours left</span><strong>{data?.progress?.hours_remaining || 0}h</strong></div>
        <div className="planner-stat"><span>Daily capacity</span><strong>{Number(data?.daily_hours || 0).toFixed(1)}h</strong></div>
      </div>

      <section className="planner-section">
        <div className="planner-section-heading"><div><span className="eyebrow">FALL-BEHIND</span><h2>What is becoming urgent?</h2></div></div>
        <div className="planner-risk-list">
          {(data?.fall_behind || []).map((item) => (
            <article className={`planner-risk planner-${item.severity}`} key={item.course_id}>
              <div className="planner-risk-icon">{item.severity === 'ok' ? <CheckCircle2 size={18}/> : <AlertTriangle size={18}/>}</div>
              <div className="planner-risk-copy">
                <strong>{item.course_code} · {item.title}</strong>
                <span>{item.required_hours}h backlog · {item.available_hours == null ? 'no target' : `${item.available_hours}h available`} · target {formatTarget(item.target_at)}</span>
              </div>
              <span className="planner-severity">{item.severity}</span>
            </article>
          ))}
          {!data?.fall_behind?.length && <div className="planner-empty">Add courses and topics to activate fall-behind detection.</div>}
        </div>
      </section>

      <div className="planner-grid">
        <section className="planner-section">
          <div className="planner-section-heading"><div><span className="eyebrow">CAPACITY</span><h2>Study hours per day</h2></div></div>
          <div className="planner-inline-form">
            <input type="number" min="0.25" max="16" step="0.25" value={dailyHours} onChange={(e) => setDailyHours(e.target.value)} />
            <button className="upload-button" onClick={saveHours}>Save capacity</button>
          </div>
        </section>

        <section className="planner-section">
          <div className="planner-section-heading"><div><span className="eyebrow">COURSES</span><h2>Add a course</h2></div></div>
          <form className="planner-form" onSubmit={addCourse}>
            <input placeholder="Code e.g. PHY" value={course.code} onChange={(e) => setCourse({ ...course, code: e.target.value })} required />
            <input placeholder="Course name" value={course.title} onChange={(e) => setCourse({ ...course, title: e.target.value })} required />
            <input type="datetime-local" value={course.deadline_at} onChange={(e) => setCourse({ ...course, deadline_at: e.target.value ? new Date(e.target.value).toISOString() : '' })} />
            <button className="upload-button" type="submit"><Plus size={15}/> Add course</button>
          </form>
        </section>
      </div>

      <section className="planner-section">
        <div className="planner-section-heading"><div><span className="eyebrow">TOPICS</span><h2>Build the backlog Apollo can measure</h2></div></div>
        <form className="planner-form planner-topic-form" onSubmit={addTopic}>
          <select value={topic.course_id} onChange={(e) => setTopic({ ...topic, course_id: e.target.value })} required>
            <option value="">Choose course</option>
            {(data?.courses || []).map((item) => <option value={item.id} key={item.id}>{item.code} · {item.title}</option>)}
          </select>
          <input placeholder="Topic / lecture" value={topic.title} onChange={(e) => setTopic({ ...topic, title: e.target.value })} required />
          <input type="number" min="0.1" max="40" step="0.25" value={topic.estimated_hours} onChange={(e) => setTopic({ ...topic, estimated_hours: e.target.value })} />
          <input type="datetime-local" value={topic.lecture_at} onChange={(e) => setTopic({ ...topic, lecture_at: e.target.value ? new Date(e.target.value).toISOString() : '' })} />
          <button className="upload-button" type="submit"><Plus size={15}/> Add topic</button>
        </form>
        <div className="planner-topic-list">
          {(data?.topics || []).map((item) => (
            <div className={`planner-topic ${item.status === 'completed' ? 'completed' : ''}`} key={item.id}>
              <div><strong>{item.title}</strong><span>{data.courses?.find((course) => course.id === item.course_id)?.code || 'Course'} · {item.estimated_hours}h {item.lecture_at ? `· ${formatTarget(item.lecture_at)}` : ''}</span></div>
              <select value={item.status} onChange={(e) => mark(item.id, e.target.value)}>
                <option value="not_started">Not started</option>
                <option value="in_progress">In progress</option>
                <option value="completed">Completed</option>
              </select>
            </div>
          ))}
        </div>
      </section>
    </main>
  )
}
