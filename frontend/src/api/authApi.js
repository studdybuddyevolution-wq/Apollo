const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'https://apollo-api-2pt1.onrender.com').replace(/\/$/, '')
const TOKEN_KEY = 'apollo-auth-token'
const USER_KEY = 'apollo-auth-user'

export function getAuthToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function getAuthUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || 'null')
  } catch {
    return null
  }
}

export function setAuthSession(payload) {
  if (payload?.access_token) localStorage.setItem(TOKEN_KEY, payload.access_token)
  if (payload?.user) localStorage.setItem(USER_KEY, JSON.stringify(payload.user))
  window.dispatchEvent(new Event('apollo-auth-changed'))
  return payload?.user || null
}

export function clearAuthSession() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
  window.dispatchEvent(new Event('apollo-auth-changed'))
}

export function getAuthHeaders(headers = {}) {
  const token = getAuthToken()
  return token ? { ...headers, Authorization: `Bearer ${token}` } : { ...headers }
}

export function authFetch(input, options = {}) {
  return fetch(input, { ...options, headers: getAuthHeaders(options.headers || {}) })
}

async function request(path, options = {}) {
  const response = await authFetch(`${API_BASE}${path}`, options)
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body?.detail || `Apollo API returned ${response.status}`)
  return body
}

export function registerAccount(email, password) {
  return request('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  }).then(setAuthSession)
}

export function loginAccount(email, password) {
  return request('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  }).then(setAuthSession)
}

export function logoutAccount() {
  clearAuthSession()
}

export async function getCurrentAccount() {
  if (!getAuthToken()) return null
  try {
    const payload = await request('/api/auth/me')
    if (payload?.user) localStorage.setItem(USER_KEY, JSON.stringify(payload.user))
    return payload?.user || null
  } catch {
    clearAuthSession()
    return null
  }
}

export function billingCheckout(priceId, urls = {}) {
  return request('/api/billing/checkout', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      price_id: priceId,
      success_url: urls.successUrl,
      cancel_url: urls.cancelUrl,
    }),
  })
}

export function getBillingStatus() {
  return request('/api/billing/me')
}
