/**
 * useAuth — frontend-only authentication hook.
 * Persists users and sessions in localStorage.
 *
 * Storage:
 *  carenexus_users   → Array<UserRecord>
 *  carenexus_session → SessionRecord | null
 *
 * UserRecord (patient):
 *  { type:'patient', fullName, memberId, mobile, email, dob, passwordHash }
 *
 * UserRecord (hospital):
 *  { type:'hospital', orgName, regId, email, mobile, address, passwordHash }
 *
 * NOTE: Passwords use a naive hash for demo only.
 * TODO: Replace with bcrypt + JWT via POST /api/auth/login when FastAPI is ready.
 */
import { useState, useCallback } from 'react'

const USERS_KEY   = 'carenexus_users'
const SESSION_KEY = 'carenexus_session'

function simpleHash(str) {
  let h = 0
  for (let i = 0; i < str.length; i++) h = (Math.imul(31, h) + str.charCodeAt(i)) | 0
  return h.toString(36)
}

const loadUsers   = () => { try { return JSON.parse(localStorage.getItem(USERS_KEY)   || '[]')   } catch { return [] } }
const loadSession = () => { try { return JSON.parse(localStorage.getItem(SESSION_KEY) || 'null') } catch { return null } }
const saveUsers   = (u) => localStorage.setItem(USERS_KEY,   JSON.stringify(u))
const saveSession = (s) => localStorage.setItem(SESSION_KEY, JSON.stringify(s))
const clearSession = ()  => localStorage.removeItem(SESSION_KEY)

export function useAuth() {
  const [session, setSession] = useState(() => loadSession())

  /* ---- registerPatient ---- */
  const registerPatient = useCallback(({ fullName, memberId, mobile, email, dob, password }) => {
    const users = loadUsers()
    if (users.some(u => u.type === 'patient' && u.memberId === memberId.trim()))
      return { ok: false, error: 'A patient account with this Member ID already exists.' }

    saveUsers([...users, {
      type: 'patient',
      fullName: fullName.trim(), memberId: memberId.trim(),
      mobile: mobile.trim(), email: email.trim().toLowerCase(), dob,
      passwordHash: simpleHash(password),
    }])
    return { ok: true }
  }, [])

  /* ---- registerHospital ---- */
  const registerHospital = useCallback(({ orgName, regId, email, mobile, address, password }) => {
    const users = loadUsers()
    if (users.some(u => u.type === 'hospital' && u.regId === regId.trim()))
      return { ok: false, error: 'A hospital with this Registration ID already exists.' }

    saveUsers([...users, {
      type: 'hospital',
      orgName: orgName.trim(), regId: regId.trim(),
      email: email.trim().toLowerCase(), mobile: mobile.trim(),
      address: address.trim(), passwordHash: simpleHash(password),
    }])
    return { ok: true }
  }, [])

  /* ---- login (unified identifier) ---- */
  const login = useCallback(({ identifier, password }, rememberMe) => {
    const users = loadUsers()
    const hash  = simpleHash(password)
    const id    = identifier.trim()

    // Try patient (Member ID)
    let user = users.find(u => u.type === 'patient' && u.memberId === id && u.passwordHash === hash)
    if (user) {
      const sess = { type: 'patient', name: user.fullName, memberId: user.memberId, email: user.email, loginTime: new Date().toISOString() }
      if (rememberMe) saveSession(sess)
      setSession(sess)
      return { ok: true, session: sess }
    }

    // Try hospital (org name)
    user = users.find(u => u.type === 'hospital' && u.orgName.toLowerCase() === id.toLowerCase() && u.passwordHash === hash)
    if (user) {
      const sess = { type: 'hospital', name: user.orgName, regId: user.regId, email: user.email, loginTime: new Date().toISOString() }
      if (rememberMe) saveSession(sess)
      setSession(sess)
      return { ok: true, session: sess }
    }

    // CMS admin: any non-empty credentials work in this demo
    // TODO: POST /api/auth/login when FastAPI is ready
    if (id.toLowerCase().startsWith('admin') && password.length >= 6) {
      const sess = { type: 'cms', name: 'Administrator', adminId: id, loginTime: new Date().toISOString() }
      if (rememberMe) saveSession(sess)
      setSession(sess)
      return { ok: true, session: sess }
    }

    return { ok: false, error: 'No account found with these credentials. Please check your identifier and password.' }
  }, [])

  /* ---- logout ---- */
  const logout = useCallback(() => { clearSession(); setSession(null) }, [])

  return { session, login, logout, registerPatient, registerHospital }
}
