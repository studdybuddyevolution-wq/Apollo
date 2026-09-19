import { authFetch } from './authApi'

const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'https://apollo-api-2pt1.onrender.com').replace(/\/$/, '')

async function request(path, options = {}) {
  const response = await authFetch(`${API_BASE}${path}`, options)
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body?.detail || `Apollo API returned ${response.status}`)
  return body
}

export const getPlannerDashboard = (userId = 'default') =>
  request(`/api/planner/dashboard?user_id=${encodeURIComponent(userId)}`)

export const setDailyStudyHours = (dailyHours, userId = 'default') =>
  request('/api/planner/preferences', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ daily_hours: dailyHours, user_id: userId }),
  })

export const createPlannerCourse = (course, userId = 'default') =>
  request('/api/planner/courses', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...course, user_id: userId }),
  })

export const createPlannerTopic = (topic, userId = 'default') =>
  request('/api/planner/topics', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...topic, user_id: userId }),
  })

export const updatePlannerTopic = (topicId, status, userId = 'default') =>
  request(`/api/planner/topics/${encodeURIComponent(topicId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status, user_id: userId }),
  })
