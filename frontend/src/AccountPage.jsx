import { useEffect, useState } from 'react'
import { LogIn, LogOut, ShieldCheck, UserPlus } from 'lucide-react'
import {
  clearAuthSession,
  getAuthUser,
  getCurrentAccount,
  getBillingStatus,
  loginAccount,
  logoutAccount,
  registerAccount,
} from './api/authApi'

export default function AccountPage() {
  const [user, setUser] = useState(() => getAuthUser())
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [billing, setBilling] = useState(null)

  useEffect(() => {
    let active = true
    getCurrentAccount().then((value) => { if (active) setUser(value) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!user) return
    getBillingStatus().then(setBilling).catch(() => setBilling(null))
  }, [user])

  const submit = async (event) => {
    event.preventDefault()
    setBusy(true)
    setMessage('')
    try {
      const payload = mode === 'login'
        ? await loginAccount(email, password)
        : await registerAccount(email, password)
      setUser(payload?.user || null)
      setPassword('')
      setMessage(mode === 'login' ? 'Signed in.' : 'Account created and signed in.')
    } catch (error) {
      setMessage(error?.message || 'Authentication failed.')
    } finally {
      setBusy(false)
    }
  }

  if (user) {
    return (
      <main className="main-content placeholder-page">
        <div className="page-heading"><div className="page-icon"><ShieldCheck size={22}/></div><div><div className="eyebrow">ACCOUNT</div><h1>{user.email}</h1><p>JWT authentication is active for Apollo's protected features.</p></div></div>
        <div className="planner-section">
          <div className="planner-stats">
            <div className="planner-stat"><span>Account</span><strong>Active</strong></div>
            <div className="planner-stat"><span>Subscription</span><strong>{billing?.subscription_status || 'Free'}</strong></div>
          </div>
          <button className="upload-button" onClick={() => { logoutAccount(); clearAuthSession(); setUser(null); setBilling(null) }}><LogOut size={15}/> Sign out</button>
        </div>
      </main>
    )
  }

  return (
    <main className="main-content placeholder-page">
      <div className="page-heading"><div className="page-icon">{mode === 'login' ? <LogIn size={22}/> : <UserPlus size={22}/>}</div><div><div className="eyebrow">ACCOUNT SECURITY</div><h1>{mode === 'login' ? 'Sign in to Apollo' : 'Create your Apollo account'}</h1><p>Use the new FastAPI-style JWT account layer for protected workspace features.</p></div></div>
      <form className="account-form" onSubmit={submit}>
        <input type="email" autoComplete="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <input type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} placeholder="Password (8+ characters)" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} />
        <button className="upload-button" disabled={busy}>{busy ? 'Working…' : mode === 'login' ? 'Sign in' : 'Create account'}</button>
      </form>
      {message && <div className="planner-message">{message}</div>}
      <button className="topbar-tool" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setMessage('') }}>{mode === 'login' ? 'Need an account? Register' : 'Already have an account? Sign in'}</button>
    </main>
  )
}
