import { useEffect, useMemo, useState } from 'react'
import {
  Activity, CalendarDays, Check, ChevronDown, Clock3, GitBranch, ListChecks,
  Plus, RefreshCw, RotateCcw, SkipForward, Sparkles, Trash2, Play,
} from 'lucide-react'
import {
  applyPlannerProposal, completePlannerBlock, createPlannerAvailability, createPlannerGoal,
  createPlannerTopic, deletePlannerAvailability, deletePlannerBlock, generatePlannerProposal,
  getPlannerOverview, listPlannerAvailability, listPlannerBlocks, listPlannerGoals, listPlannerTopics,
  movePlannerBlock, replanPlanner, skipPlannerBlock, updatePlannerTopic,
} from './api/plannerApi'
import './study-planner.css'

const DAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

function todayIso() {
  return new Date().toISOString().slice(0, 10)
}

function addDays(dateIso, amount) {
  const date = new Date(dateIso + 'T12:00:00')
  date.setDate(date.getDate() + amount)
  return date.toISOString().slice(0, 10)
}

function minutesLabel(value) {
  const minutes = Math.max(0, Number(value) || 0)
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  if (!hours) return rest + 'm'
  return rest ? hours + 'h ' + rest + 'm' : hours + 'h'
}

function dateLabel(value, options) {
  return new Intl.DateTimeFormat(undefined, options || { weekday: 'short', month: 'short', day: 'numeric' }).format(new Date(value + 'T12:00:00'))
}

function depthForTopic(topic, byId) {
  let depth = 0
  let cursor = topic
  while (cursor && cursor.parent_id && depth < 8) {
    cursor = byId[cursor.parent_id]
    depth += 1
  }
  return depth
}

export default function StudyPlannerPage({ userId = 'default', notebooks = [], activeNotebookId = '', onStartStudy }) {
  const [goals, setGoals] = useState([])
  const [topics, setTopics] = useState([])
  const [availability, setAvailability] = useState([])
  const [blocks, setBlocks] = useState([])
  const [overview, setOverview] = useState(null)
  const [proposal, setProposal] = useState(null)
  const [selectedGoalId, setSelectedGoalId] = useState('')
  const [section, setSection] = useState('overview')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [goalForm, setGoalForm] = useState({ title: '', subject: '', exam_date: '', priority: 3 })
  const [topicForm, setTopicForm] = useState({ title: '', goal_id: '', parent_id: '', estimated_minutes: 45, difficulty: 3 })
  const [availabilityForm, setAvailabilityForm] = useState({ weekday: 1, start_time: '17:00', end_time: '19:00' })
  const [importOpen, setImportOpen] = useState(false)
  const [importText, setImportText] = useState('')

  const weekStart = todayIso()
  const weekDates = useMemo(() => Array.from({ length: 7 }, (_, index) => addDays(weekStart, index)), [weekStart])
  const goalsById = useMemo(() => Object.fromEntries(goals.map((item) => [item.id, item])), [goals])
  const topicsById = useMemo(() => Object.fromEntries(topics.map((item) => [item.id, item])), [topics])
  const orderedTopics = useMemo(() => [...topics].sort((a, b) => (
    depthForTopic(a, topicsById) - depthForTopic(b, topicsById)
    || String(a.goal_id || '').localeCompare(String(b.goal_id || ''))
    || Number(a.sort_order || 0) - Number(b.sort_order || 0)
    || String(a.title || '').localeCompare(String(b.title || ''))
  )), [topics, topicsById])

  const refresh = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await Promise.all([
        listPlannerGoals(userId),
        listPlannerTopics(userId),
        listPlannerAvailability(userId),
        listPlannerBlocks(userId, weekStart, addDays(weekStart, 30)),
        getPlannerOverview(userId, 7),
      ])
      setGoals(data[0].goals || [])
      setTopics(data[1].topics || [])
      setAvailability(data[2].availability || [])
      setBlocks(data[3].blocks || [])
      setOverview(data[4])
      setSelectedGoalId((current) => current || data[0].goals?.find((item) => item.status === 'active')?.id || '')
    } catch (err) {
      setError(err?.message || 'Planner data could not be loaded')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { refresh() }, [userId])
  useEffect(() => { setTopicForm((current) => ({ ...current, goal_id: current.goal_id || selectedGoalId })) }, [selectedGoalId])

  const selectedGoal = goalsById[selectedGoalId] || goals.find((item) => item.status === 'active') || null
  const activeNotebook = notebooks.find((item) => item.id === activeNotebookId)
  const goalOptions = goals.filter((item) => item.status === 'active')

  const createGoal = async (event) => {
    event.preventDefault()
    if (!goalForm.title.trim()) return
    setBusy(true)
    try {
      const created = await createPlannerGoal({
        title: goalForm.title.trim(),
        subject: goalForm.subject.trim(),
        exam_date: goalForm.exam_date || null,
        priority: Number(goalForm.priority),
      }, userId)
      setGoals((current) => [created, ...current])
      setSelectedGoalId(created.id)
      setGoalForm({ title: '', subject: '', exam_date: '', priority: 3 })
    } catch (err) {
      setError(err?.message || 'Goal creation failed')
    } finally { setBusy(false) }
  }

  const createTopic = async (event) => {
    event.preventDefault()
    if (!topicForm.title.trim()) return
    setBusy(true)
    try {
      const created = await createPlannerTopic({
        title: topicForm.title.trim(),
        goal_id: topicForm.goal_id || null,
        parent_id: topicForm.parent_id || null,
        estimated_minutes: Number(topicForm.estimated_minutes),
        difficulty: Number(topicForm.difficulty),
      }, userId)
      setTopics((current) => [...current, created])
      setTopicForm((current) => ({ ...current, title: '' }))
    } catch (err) {
      setError(err?.message || 'Topic creation failed')
    } finally { setBusy(false) }
  }

  const importCurriculum = async () => {
    const lines = importText.split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
    if (!lines.length) return
    setBusy(true)
    setError('')
    try {
      let working = [...topics]
      for (const line of lines) {
        const columns = line.split('|').map((value) => value.trim())
        const path = columns[0].split('>').map((value) => value.trim()).filter(Boolean)
        const estimated = Number(columns[1] || 45)
        const difficulty = Number(columns[2] || 3)
        let parentId = null
        for (const title of path) {
          const existing = working.find((topic) => (
            (topic.goal_id || null) === (selectedGoalId || topicForm.goal_id || null)
            && (topic.parent_id || null) === parentId
            && String(topic.title).toLowerCase() === title.toLowerCase()
          ))
          if (existing) {
            parentId = existing.id
            continue
          }
          const created = await createPlannerTopic({
            title,
            goal_id: selectedGoalId || topicForm.goal_id || null,
            parent_id: parentId,
            estimated_minutes: path[path.length - 1] === title ? Math.max(5, Math.min(720, estimated || 45)) : 45,
            difficulty: Math.max(1, Math.min(5, difficulty || 3)),
          }, userId)
          working = [...working, created]
          parentId = created.id
        }
      }
      setTopics(working)
      setImportText('')
      setImportOpen(false)
    } catch (err) {
      setError(err?.message || 'Curriculum import failed')
    } finally { setBusy(false) }
  }

  const addAvailability = async (event) => {
    event.preventDefault()
    setBusy(true)
    try {
      const created = await createPlannerAvailability({
        weekday: Number(availabilityForm.weekday),
        start_time: availabilityForm.start_time,
        end_time: availabilityForm.end_time,
        enabled: true,
      }, userId)
      setAvailability((current) => [...current, created])
    } catch (err) {
      setError(err?.message || 'Availability could not be saved')
    } finally { setBusy(false) }
  }

  const generate = async (replanMode) => {
    setBusy(true)
    setError('')
    try {
      const payload = {
        goal_ids: selectedGoalId ? [selectedGoalId] : [],
        horizon_days: 14,
        start_date: todayIso(),
        notebook_id: activeNotebookId || null,
      }
      const next = replanMode ? await replanPlanner(payload, userId) : await generatePlannerProposal(payload, userId)
      setProposal(next)
      setSection('proposal')
    } catch (err) {
      setError(err?.message || 'The planner could not generate a proposal')
    } finally { setBusy(false) }
  }

  const updateProposalBlock = (index, changes) => {
    setProposal((current) => current ? ({
      ...current,
      blocks: current.blocks.map((item, rowIndex) => rowIndex === index ? { ...item, ...changes } : item),
    }) : current)
  }

  const acceptProposal = async () => {
    if (!proposal) return
    setBusy(true)
    try {
      await applyPlannerProposal({
        ...proposal,
        total_planned_minutes: proposal.blocks.reduce((sum, block) => sum + Number(block.duration_minutes || 0), 0),
      }, userId)
      setProposal(null)
      await refresh()
      setSection('calendar')
    } catch (err) {
      setError(err?.message || 'The plan could not be applied')
    } finally { setBusy(false) }
  }

  const removeProposalBlock = (index) => {
    setProposal((current) => current ? { ...current, blocks: current.blocks.filter((_, i) => i !== index) } : current)
  }

  const completeBlock = async (block) => {
    const actual = window.prompt('Actual minutes studied?', String(block.duration_minutes || 0))
    if (actual === null) return
    setBusy(true)
    try {
      await completePlannerBlock(block.id, Number(actual), userId)
      await refresh()
    } catch (err) {
      setError(err?.message || 'Block could not be completed')
    } finally { setBusy(false) }
  }

  const skipBlock = async (block) => {
    setBusy(true)
    try {
      await skipPlannerBlock(block.id, userId)
      await refresh()
    } catch (err) {
      setError(err?.message || 'Block could not be skipped')
    } finally { setBusy(false) }
  }

  const moveBlock = async (block) => {
    const newDate = window.prompt('New date (YYYY-MM-DD)', block.planned_date)
    if (!newDate) return
    const newTime = window.prompt('New start time (HH:MM, optional)', block.start_time ? block.start_time.slice(0, 5) : '')
    setBusy(true)
    try {
      await movePlannerBlock(block.id, newDate, newTime || null, userId)
      await refresh()
    } catch (err) {
      setError(err?.message || 'Block could not be moved')
    } finally { setBusy(false) }
  }

  const deleteAvailability = async (row) => {
    setBusy(true)
    try {
      await deletePlannerAvailability(row.id, userId)
      setAvailability((current) => current.filter((item) => item.id !== row.id))
    } catch (err) {
      setError(err?.message || 'Availability could not be deleted')
    } finally { setBusy(false) }
  }

  const toggleTopicCompletion = async (topic) => {
    setBusy(true)
    try {
      const updated = await updatePlannerTopic(topic.id, { status: topic.status === 'completed' ? 'pending' : 'completed' }, userId)
      setTopics((current) => current.map((item) => item.id === topic.id ? updated : item))
    } catch (err) {
      setError(err?.message || 'Topic status could not be updated')
    } finally { setBusy(false) }
  }

  const capacityForDate = (iso) => {
    const weekday = new Date(iso + 'T12:00:00').getDay()
    return availability.filter((row) => Number(row.weekday) === weekday && row.enabled).reduce((sum, row) => {
      const start = row.start_time.slice(0, 5).split(':').map(Number)
      const end = row.end_time.slice(0, 5).split(':').map(Number)
      return sum + Math.max(0, end[0] * 60 + end[1] - (start[0] * 60 + start[1]))
    }, 0)
  }

  const blocksForDate = (iso) => blocks.filter((item) => item.planned_date === iso)
  const plannedForDate = (iso) => blocksForDate(iso).filter((item) => item.status !== 'skipped').reduce((sum, item) => sum + Number(item.duration_minutes || 0), 0)

  if (loading) return <main className="planner-page"><div className="planner-loading"><RefreshCw className="spin" size={18} /> Loading Study Planner…</div></main>

  return (
    <main className="planner-page">
      <div className="planner-header">
        <div><div className="eyebrow">MARKLYF PLANNER</div><h1>Study Planner</h1><p>Deterministic scheduling around your goals, curriculum and real study capacity.</p></div>
        <div className="planner-header-actions">
          {activeNotebook && <span className="planner-context">Workspace: <strong>{activeNotebook.title}</strong></span>}
          <button className="planner-primary" onClick={() => generate(false)} disabled={busy}><Sparkles size={14} /> Generate plan</button>
          <button className="planner-secondary" onClick={() => generate(true)} disabled={busy}><RotateCcw size={14} /> Replan</button>
        </div>
      </div>

      {error && <div className="planner-error">{error}</div>}

      <div className="planner-tabs">
        {[
          ['overview', 'Overview', Activity],
          ['goals', 'Goals & Curriculum', ListChecks],
          ['availability', 'Availability', Clock3],
          ['proposal', 'Proposal', Sparkles],
          ['calendar', 'Week', CalendarDays],
        ].map(([id, label, Icon]) => <button key={id} className={section === id ? 'active' : ''} onClick={() => setSection(id)}><Icon size={14} /> {label}</button>)}
      </div>

      {section === 'overview' && (
        <section className="planner-grid">
          <article className="planner-card planner-hero-card">
            <div className="planner-card-head"><div><span className="planner-label">CURRENT GOAL</span><h2>{selectedGoal?.title || 'Create your first study goal'}</h2></div><GitBranch size={18} /></div>
            {selectedGoal ? <><p>{selectedGoal.subject || 'General study'} {selectedGoal.exam_date ? '· target ' + dateLabel(selectedGoal.exam_date) : '· no fixed deadline'}</p><div className="planner-stat-row"><div><strong>{minutesLabel(overview?.weekly_workload_minutes)}</strong><span>planned</span></div><div><strong>{minutesLabel(overview?.weekly_completed_minutes)}</strong><span>completed</span></div><div><strong>{Number(overview?.completion_percentage || 0).toFixed(0)}%</strong><span>completion</span></div></div></> : <p>Create a goal, add topics and define study windows before generating a plan.</p>}
          </article>
          <article className="planner-card"><div className="planner-card-head"><span className="planner-label">DEADLINE</span><CalendarDays size={18} /></div><h2>{overview?.current_goal?.exam_date ? dateLabel(overview.current_goal.exam_date) : 'No deadline yet'}</h2><p>{overview?.deadline_warnings?.[0] || 'No immediate deadline warning.'}</p></article>
          <article className="planner-card"><div className="planner-card-head"><span className="planner-label">UPCOMING BLOCKS</span><Clock3 size={18} /></div><div className="planner-list">{(overview?.upcoming_blocks || []).slice(0, 5).map((block) => <div className="planner-list-row" key={block.id}><span>{dateLabel(block.planned_date, { month: 'short', day: 'numeric' })}</span><strong>{block.title}</strong><span>{minutesLabel(block.duration_minutes)}</span></div>)}{!overview?.upcoming_blocks?.length && <div className="planner-empty">No accepted blocks yet.</div>}</div></article>
          <article className="planner-card"><div className="planner-card-head"><span className="planner-label">PLANNING SIGNALS</span><Activity size={18} /></div>{(overview?.deadline_warnings || []).map((warning) => <p className="planner-warning" key={warning}>{warning}</p>)}{!overview?.deadline_warnings?.length && <p>No active deadline warnings.</p>}</article>
        </section>
      )}

      {section === 'goals' && (
        <section className="planner-grid two">
          <article className="planner-card">
            <div className="planner-card-head"><span className="planner-label">NEW GOAL</span><Plus size={18} /></div>
            <form className="planner-form" onSubmit={createGoal}>
              <input placeholder="Goal title" value={goalForm.title} onChange={(e) => setGoalForm({ ...goalForm, title: e.target.value })} />
              <input placeholder="Subject" value={goalForm.subject} onChange={(e) => setGoalForm({ ...goalForm, subject: e.target.value })} />
              <label>Target date<input type="date" value={goalForm.exam_date} onChange={(e) => setGoalForm({ ...goalForm, exam_date: e.target.value })} /></label>
              <label>Priority<select value={goalForm.priority} onChange={(e) => setGoalForm({ ...goalForm, priority: Number(e.target.value) })}>{[1,2,3,4,5].map((value) => <option key={value} value={value}>{value}/5</option>)}</select></label>
              <button className="planner-primary" disabled={busy}><Plus size={14} /> Create goal</button>
            </form>
          </article>
          <article className="planner-card planner-wide">
            <div className="planner-card-head"><span className="planner-label">CURRICULUM / TOPICS</span><ListChecks size={18} /></div>
            <form className="planner-form topic-form" onSubmit={createTopic}>
              <input placeholder="Topic name" value={topicForm.title} onChange={(e) => setTopicForm({ ...topicForm, title: e.target.value })} />
              <select value={topicForm.goal_id} onChange={(e) => setTopicForm({ ...topicForm, goal_id: e.target.value })}><option value="">No goal</option>{goalOptions.map((goal) => <option key={goal.id} value={goal.id}>{goal.title}</option>)}</select>
              <select value={topicForm.parent_id} onChange={(e) => setTopicForm({ ...topicForm, parent_id: e.target.value })}><option value="">Top-level topic</option>{topics.map((topic) => <option key={topic.id} value={topic.id}>{topic.title}</option>)}</select>
              <input type="number" min="5" step="5" value={topicForm.estimated_minutes} onChange={(e) => setTopicForm({ ...topicForm, estimated_minutes: Number(e.target.value) })} />
              <select value={topicForm.difficulty} onChange={(e) => setTopicForm({ ...topicForm, difficulty: Number(e.target.value) })}>{[1,2,3,4,5].map((value) => <option key={value} value={value}>Difficulty {value}</option>)}</select>
              <button className="planner-primary" disabled={busy}><Plus size={14} /> Add topic</button>
              <button type="button" className="planner-secondary" onClick={() => setImportOpen((value) => !value)} disabled={busy}><GitBranch size={14} /> Import</button>
            </form>
            <div className="planner-topic-tree">{orderedTopics.map((topic) => <div className="planner-topic-row" key={topic.id} style={{ paddingLeft: 12 + depthForTopic(topic, topicsById) * 22 }}><button className={topic.status === 'completed' ? 'topic-check done' : 'topic-check'} onClick={() => toggleTopicCompletion(topic)} title="Toggle completion"><Check size={13} /></button><div className="planner-topic-main"><strong className={topic.status === 'completed' ? 'completed' : ''}>{topic.title}</strong><span>{goalOptions.find((goal) => goal.id === topic.goal_id)?.title || 'Unassigned'} · {minutesLabel(topic.estimated_minutes)} · difficulty {topic.difficulty}/5</span></div></div>)}{!orderedTopics.length && <div className="planner-empty">No topics yet.</div>}</div>
          </article>
          <article className="planner-card planner-wide">
            <div className="planner-card-head"><span className="planner-label">GOAL SELECTION</span><ListChecks size={18} /></div>
            <select className="planner-large-select" value={selectedGoalId} onChange={(e) => setSelectedGoalId(e.target.value)}><option value="">All active goals</option>{goalOptions.map((goal) => <option key={goal.id} value={goal.id}>{goal.title}{goal.exam_date ? ' · ' + dateLabel(goal.exam_date, { month: 'short', day: 'numeric' }) : ''}</option>)}</select>
          </article>
        </section>
      )}

      {section === 'availability' && (
        <section className="planner-grid two">
          <article className="planner-card">
            <div className="planner-card-head"><span className="planner-label">ADD STUDY WINDOW</span><Clock3 size={18} /></div>
            <form className="planner-form" onSubmit={addAvailability}>
              <label>Weekday<select value={availabilityForm.weekday} onChange={(e) => setAvailabilityForm({ ...availabilityForm, weekday: Number(e.target.value) })}>{DAY_NAMES.map((name, index) => <option key={name} value={index}>{name}</option>)}</select></label>
              <label>Start<input type="time" value={availabilityForm.start_time} onChange={(e) => setAvailabilityForm({ ...availabilityForm, start_time: e.target.value })} /></label>
              <label>End<input type="time" value={availabilityForm.end_time} onChange={(e) => setAvailabilityForm({ ...availabilityForm, end_time: e.target.value })} /></label>
              <button className="planner-primary" disabled={busy}><Plus size={14} /> Add window</button>
            </form>
          </article>
          <article className="planner-card planner-wide">
            <div className="planner-card-head"><span className="planner-label">WEEKLY CAPACITY</span><Clock3 size={18} /></div>
            <div className="planner-capacity-list">{DAY_NAMES.map((name, index) => {
              const rows = availability.filter((row) => Number(row.weekday) === index && row.enabled)
              const total = rows.reduce((sum, row) => {
                const start = row.start_time.slice(0, 5).split(':').map(Number)
                const end = row.end_time.slice(0, 5).split(':').map(Number)
                return sum + Math.max(0, end[0] * 60 + end[1] - (start[0] * 60 + start[1]))
              }, 0)
              return <div className="planner-capacity-row" key={name}><strong>{name}</strong><span>{minutesLabel(total)}</span><div className="planner-window-pills">{rows.map((row) => <button key={row.id} onClick={() => deleteAvailability(row)}>{row.start_time.slice(0, 5)}–{row.end_time.slice(0, 5)} <Trash2 size={10} /></button>)}</div></div>
            })}</div>
          </article>
        </section>
      )}

      {section === 'proposal' && (
        <section className="planner-proposal">
          {!proposal ? <div className="planner-card planner-empty-state"><Sparkles size={28} /><h2>No active proposal</h2><p>Generate a plan first. Nothing is stored until you accept it.</p><button className="planner-primary" onClick={() => generate(false)} disabled={busy}><Sparkles size={14} /> Generate proposal</button></div> : <>
            <div className="planner-card"><div className="planner-card-head"><div><span className="planner-label">PLAN PROPOSAL</span><h2>{proposal.blocks.length} block(s)</h2></div><span className="planner-proposal-badge">Nothing saved yet</span></div><div className="planner-proposal-summary"><span>Capacity {minutesLabel(proposal.available_capacity_minutes)}</span><span>Planned {minutesLabel(proposal.blocks.reduce((sum, item) => sum + Number(item.duration_minutes || 0), 0))}</span><span>Unscheduled {minutesLabel((proposal.unscheduled_work || []).reduce((sum, item) => sum + Number(item.remaining_minutes || 0), 0))}</span></div>{(proposal.warnings || []).map((warning) => <div className="planner-warning" key={warning}>{warning}</div>)}</div>
            <div className="planner-proposal-list">{proposal.blocks.map((block, index) => <article className="planner-card proposal-row" key={block.id || index}><div className="proposal-dot"><Clock3 size={16} /></div><div className="proposal-main"><strong>{block.title}</strong><span>{goalsById[block.goal_id]?.title || 'General goal'} · {block.reason}</span></div><input type="date" value={block.planned_date} onChange={(e) => updateProposalBlock(index, { planned_date: e.target.value })} /><input type="time" value={block.start_time ? block.start_time.slice(0, 5) : ''} onChange={(e) => updateProposalBlock(index, { start_time: e.target.value || null })} /><input type="number" min="5" step="5" value={block.duration_minutes} onChange={(e) => updateProposalBlock(index, { duration_minutes: Number(e.target.value) })} /><button className="icon-only" onClick={() => removeProposalBlock(index)} title="Remove proposed block"><Trash2 size={14} /></button></article>)}</div>
            {(proposal.unscheduled_work || []).map((item) => <div className="planner-unscheduled" key={item.topic_id}><strong>{item.title}</strong><span>{minutesLabel(item.remaining_minutes)} could not fit · {item.reason}</span></div>)}
            <div className="planner-sticky-actions"><button className="planner-primary" onClick={acceptProposal} disabled={busy}><Check size={14} /> Accept plan</button><button className="planner-secondary" onClick={() => generate(false)} disabled={busy}><RefreshCw size={14} /> Regenerate</button><button className="planner-secondary" onClick={() => setProposal(null)} disabled={busy}>Discard</button></div>
          </>}
        </section>
      )}

      {section === 'calendar' && <section><div className="planner-week">{weekDates.map((iso) => {
        const dayBlocks = blocksForDate(iso)
        const capacity = capacityForDate(iso)
        const used = plannedForDate(iso)
        const width = capacity ? Math.min(100, (used / capacity) * 100) : 0
        return <article className="planner-day" key={iso}>
          <div className="planner-day-head"><div><strong>{dateLabel(iso, { weekday: 'short' })}</strong><span>{dateLabel(iso, { month: 'short', day: 'numeric' })}</span></div><span className={used > capacity ? 'over' : ''}>{minutesLabel(used)} / {minutesLabel(capacity)}</span></div>
          <div className="planner-day-bar"><span style={{ width: width + '%' }} /></div>
          <div className="planner-day-blocks">{dayBlocks.map((block) => <div key={block.id} className={'planner-block status-' + block.status}>
            <div className="planner-block-time">{block.start_time ? block.start_time.slice(0, 5) : 'Flexible'} · {minutesLabel(block.duration_minutes)}</div>
            <strong>{block.title}</strong>
            <span>{block.status === 'completed' ? 'Completed · ' + minutesLabel(block.actual_minutes) : block.generated_by === 'manual' ? 'Manual' : 'Generated'}</span>
            <div className="planner-block-actions">
              {block.status === 'planned' && <button onClick={() => onStartStudy?.(block)}><Play size={11} /> Start study</button>}
              {block.status === 'planned' && <button onClick={() => completeBlock(block)}><Check size={11} /> Complete</button>}
              {block.status === 'planned' && <button onClick={() => skipBlock(block)}><SkipForward size={11} /> Skip</button>}
              {block.status === 'planned' && <button onClick={() => moveBlock(block)}><ChevronDown size={11} /> Move</button>}
              <button onClick={async () => { await deletePlannerBlock(block.id, userId); await refresh() }}><Trash2 size={11} /></button>
            </div>
          </div>)}{!dayBlocks.length && <div className="planner-day-empty">Open capacity</div>}</div>
        </article>
      })}</div></section>}
    </main>
  )
}
