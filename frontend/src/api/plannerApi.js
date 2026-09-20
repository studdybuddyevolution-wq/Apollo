const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'https://apollo-api-2pt1.onrender.com').replace(/\/$/, '')

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body?.detail || `Marklyf API returned ${response.status}`)
  }
  return response.json()
}

function jsonRequest(path, method, body) {
  return request(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function listPlannerGoals(userId = 'default') {
  return request(`/api/planner/goals?user_id=${encodeURIComponent(userId)}`)
}

export function createPlannerGoal(goal, userId = 'default') {
  return jsonRequest('/api/planner/goals', 'POST', { ...goal, user_id: userId })
}

export function updatePlannerGoal(id, changes, userId = 'default') {
  return jsonRequest(`/api/planner/goals/${encodeURIComponent(id)}`, 'PATCH', { ...changes, user_id: userId })
}

export function deletePlannerGoal(id, userId = 'default') {
  return request(`/api/planner/goals/${encodeURIComponent(id)}?user_id=${encodeURIComponent(userId)}`, { method: 'DELETE' })
}

export function listPlannerTopics(userId = 'default', goalId = '') {
  const suffix = goalId ? `&goal_id=${encodeURIComponent(goalId)}` : ''
  return request(`/api/planner/topics?user_id=${encodeURIComponent(userId)}${suffix}`)
}

export function createPlannerTopic(topic, userId = 'default') {
  return jsonRequest('/api/planner/topics', 'POST', { ...topic, user_id: userId })
}

export function updatePlannerTopic(id, changes, userId = 'default') {
  return jsonRequest(`/api/planner/topics/${encodeURIComponent(id)}`, 'PATCH', { ...changes, user_id: userId })
}

export function deletePlannerTopic(id, userId = 'default') {
  return request(`/api/planner/topics/${encodeURIComponent(id)}?user_id=${encodeURIComponent(userId)}`, { method: 'DELETE' })
}

export function listPlannerAvailability(userId = 'default') {
  return request(`/api/planner/availability?user_id=${encodeURIComponent(userId)}`)
}

export function createPlannerAvailability(window, userId = 'default') {
  return jsonRequest('/api/planner/availability', 'POST', { ...window, user_id: userId })
}

export function updatePlannerAvailability(id, changes, userId = 'default') {
  return jsonRequest(`/api/planner/availability/${encodeURIComponent(id)}`, 'PATCH', { ...changes, user_id: userId })
}

export function deletePlannerAvailability(id, userId = 'default') {
  return request(`/api/planner/availability/${encodeURIComponent(id)}?user_id=${encodeURIComponent(userId)}`, { method: 'DELETE' })
}

export function listPlannerBlocks(userId = 'default', startDate = '', endDate = '') {
  const params = new URLSearchParams({ user_id: userId })
  if (startDate) params.set('start_date', startDate)
  if (endDate) params.set('end_date', endDate)
  return request(`/api/planner/blocks?${params.toString()}`)
}

export function createPlannerBlock(block, userId = 'default') {
  return jsonRequest('/api/planner/blocks', 'POST', { ...block, user_id: userId })
}

export function updatePlannerBlock(id, changes, userId = 'default') {
  return jsonRequest(`/api/planner/blocks/${encodeURIComponent(id)}`, 'PATCH', { ...changes, user_id: userId })
}

export function deletePlannerBlock(id, userId = 'default') {
  return request(`/api/planner/blocks/${encodeURIComponent(id)}?user_id=${encodeURIComponent(userId)}`, { method: 'DELETE' })
}

export function startPlannerBlock(id, userId = 'default') {
  return jsonRequest(`/api/planner/blocks/${encodeURIComponent(id)}/start?user_id=${encodeURIComponent(userId)}`, 'POST', {})
}

export function completePlannerBlock(id, actualMinutes = null, userId = 'default') {
  return jsonRequest(`/api/planner/blocks/${encodeURIComponent(id)}/complete`, 'POST', { actual_minutes: actualMinutes, user_id: userId })
}

export function skipPlannerBlock(id, userId = 'default') {
  return jsonRequest(`/api/planner/blocks/${encodeURIComponent(id)}/skip`, 'POST', { user_id: userId })
}

export function movePlannerBlock(id, plannedDate, startTime = null, userId = 'default') {
  return jsonRequest(`/api/planner/blocks/${encodeURIComponent(id)}/move`, 'POST', {
    planned_date: plannedDate,
    start_time: startTime,
    user_id: userId,
  })
}

export function generatePlannerProposal(payload, userId = 'default') {
  return jsonRequest('/api/planner/proposals', 'POST', { ...payload, user_id: userId })
}

export function applyPlannerProposal(proposal, userId = 'default') {
  return jsonRequest('/api/planner/proposals/apply', 'POST', { proposal, user_id: userId })
}

export function replanPlanner(payload, userId = 'default') {
  return jsonRequest('/api/planner/replan', 'POST', { ...payload, user_id: userId })
}

export function getPlannerOverview(userId = 'default', days = 7) {
  return request(`/api/planner/overview?user_id=${encodeURIComponent(userId)}&days=${encodeURIComponent(days)}`)
}
