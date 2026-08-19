import { useState } from 'react'
import { ChevronLeft, ShieldCheck, LogIn, User, Hospital } from 'lucide-react'
import FormInput from '../components/FormInput'
import PasswordInput from '../components/PasswordInput'
import styles from './LoginPage.module.css'

export default function LoginPage({ onLogin, onPatientRegister, onHospitalRegister, onBack }) {
  const [fields, setFields]       = useState({ identifier: '', password: '' })
  const [errors, setErrors]       = useState({ identifier: '', password: '' })
  const [rememberMe, setRemember] = useState(false)
  const [loading, setLoading]     = useState(false)
  const [submitErr, setSubmitErr] = useState('')

  const handle = (f) => (e) => {
    const v = e.target.value
    setFields(p => ({ ...p, [f]: v }))
    if (errors[f] && v.trim()) setErrors(p => ({ ...p, [f]: '' }))
  }

  const validate = () => {
    const e = { identifier: '', password: '' }
    let ok = true
    if (!fields.identifier.trim()) { e.identifier = 'Please enter your identifier.'; ok = false }
    if (!fields.password)          { e.password   = 'Please enter your password.';   ok = false }
    setErrors(e)
    return ok
  }

  const handleSubmit = async (ev) => {
    ev.preventDefault()
    setSubmitErr('')
    if (!validate()) return
    setLoading(true)
    await new Promise(r => setTimeout(r, 700))
    const result = onLogin({ identifier: fields.identifier, password: fields.password }, rememberMe)
    if (!result.ok) setSubmitErr(result.error)
    setLoading(false)
  }

  return (
    <div className={styles.page}>
      {/* Left brand panel */}
      <aside className={styles.brand} aria-label="CTS Healthcare">
        <button className={styles.back} onClick={onBack}>
          <ChevronLeft size={16} strokeWidth={2}/> Back to Home
        </button>

        <div className={styles.brandLogo}>
          <svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true">
            <rect width="40" height="40" rx="8" fill="rgba(255,255,255,0.1)"/>
            <rect x="15" y="6"  width="10" height="28" rx="2.5" fill="white"/>
            <rect x="6"  y="15" width="28" height="10" rx="2.5" fill="white"/>
          </svg>
          <div>
            <div className={styles.brandName}>CTS Healthcare</div>
            <div className={styles.brandSub}>Connected Healthcare Platform</div>
          </div>
        </div>

        <div className={styles.brandMsg}>
          <h1 className={styles.brandHeadline}>One Platform.<br/>Connected Healthcare.</h1>
          <p className={styles.brandText}>
            Your account connects you to the healthcare services relevant to you —
            patients, hospitals, and administrators all enter here.
          </p>
        </div>

        <div className={styles.brandIllustration} aria-hidden="true">
          <BrandDiagram />
        </div>

        <div className={styles.brandFeatures} role="list">
          {[
            { icon: <User       size={14} strokeWidth={2}/>, label: 'Patient Access' },
            { icon: <ShieldCheck size={14} strokeWidth={2}/>, label: 'Secure Platform' },
            { icon: <LogIn      size={14} strokeWidth={2}/>, label: 'Unified Entry' },
          ].map(f => (
            <div key={f.label} className={styles.brandPill} role="listitem">
              <span aria-hidden="true">{f.icon}</span>
              <span>{f.label}</span>
            </div>
          ))}
        </div>
      </aside>

      {/* Right form panel */}
      <main className={styles.form} aria-label="Sign in to CTS Healthcare">
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.heading}>Welcome Back</h2>
            <p className={styles.subheading}>Sign in to continue to your healthcare experience.</p>
          </div>

          {submitErr && (
            <div className={styles.errBanner} role="alert" aria-live="assertive">
              <ShieldCheck size={15} strokeWidth={2}/> {submitErr}
            </div>
          )}

          <form onSubmit={handleSubmit} noValidate>
            <div className={styles.fields}>
              <FormInput
                id="identifier"
                label="Identifier"
                placeholder="Member ID, Organization Name, or Admin ID"
                value={fields.identifier}
                onChange={handle('identifier')}
                error={errors.identifier}
                disabled={loading}
                autoComplete="username"
                icon={<User size={16} strokeWidth={2}/>}
              />
              <PasswordInput
                id="login-password"
                label="Password"
                placeholder="Enter your password"
                value={fields.password}
                onChange={handle('password')}
                error={errors.password}
                disabled={loading}
              />
            </div>

            <div className={styles.options}>
              <label className={styles.remember}>
                <input type="checkbox" className={styles.checkbox}
                  checked={rememberMe} onChange={e => setRemember(e.target.checked)}
                  disabled={loading} aria-label="Remember me"/>
                <span>Remember me</span>
              </label>
              <button type="button" className={styles.forgot}
                onClick={() => alert('Forgot password — backend integration pending.')}>
                Forgot Password?
              </button>
            </div>

            <button type="submit" className={styles.submit} disabled={loading}
              aria-label={loading ? 'Signing in…' : 'Sign In'}>
              {loading
                ? <><span className={styles.spin} aria-hidden="true"/>Signing In…</>
                : 'Sign In'
              }
            </button>
          </form>

          {/* Registration links — clean, not inside a card */}
          <div className={styles.reg}>
            <p className={styles.regLabel}>New to CTS Healthcare?</p>
            <div className={styles.regLinks}>
              <button className={styles.regBtn} onClick={onPatientRegister} type="button">
                <User size={14} strokeWidth={2}/> Register as a Patient
              </button>
              <span className={styles.regDivider} aria-hidden="true">·</span>
              <button className={styles.regBtn} onClick={onHospitalRegister} type="button">
                <Hospital size={14} strokeWidth={2}/> Register your Hospital
              </button>
            </div>
            <p className={styles.adminNote}>
              CMS / Admin accounts are provisioned by system administrators only.
            </p>
          </div>

          <footer className={styles.footer}>
            © 2026 CTS Healthcare. All rights reserved.
          </footer>
        </div>
      </main>
    </div>
  )
}

function BrandDiagram() {
  const HUB   = { cx: 130, cy: 112, r: 30 }
  const NODES = [
    { cx: 38,  cy: 38,  r: 22, label: 'Patient',  labelDY: -14 },
    { cx: 222, cy: 38,  r: 22, label: 'Hospital', labelDY: -14 },
    { cx: 130, cy: 196, r: 22, label: 'Admin',    labelDY:  16 },
  ]

  function lineFrom(node) {
    const dx = node.cx - HUB.cx
    const dy = node.cy - HUB.cy
    const dist = Math.sqrt(dx * dx + dy * dy)
    const ux = dx / dist, uy = dy / dist
    return {
      x1: HUB.cx + ux * HUB.r,
      y1: HUB.cy + uy * HUB.r,
      x2: node.cx - ux * node.r,
      y2: node.cy - uy * node.r,
    }
  }

  return (
    <svg
      viewBox="0 -15 260 245"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={styles.diagramSvg}
      role="img"
      aria-label="CTS Healthcare — Patient, Hospital, and Admin nodes connected to a central hub"
    >
      <circle cx={HUB.cx} cy={HUB.cy} r="80"  stroke="rgba(0,110,182,0.12)" strokeWidth="1"/>
      <circle cx={HUB.cx} cy={HUB.cy} r="108" stroke="rgba(0,110,182,0.06)" strokeWidth="1"/>

      {NODES.map(n => {
        const { x1, y1, x2, y2 } = lineFrom(n)
        return (
          <line key={n.label}
            x1={x1} y1={y1} x2={x2} y2={y2}
            stroke="#3BB7B2" strokeWidth="1.25"
            strokeDasharray="5 4" opacity="0.55"
          />
        )
      })}

      {NODES.map(n => {
        const labelY = n.labelDY < 0
          ? n.cy - n.r + n.labelDY
          : n.cy + n.r + n.labelDY

        return (
          <g key={n.label}>
            <circle
              cx={n.cx} cy={n.cy} r={n.r}
              fill="rgba(255,255,255,0.06)"
              stroke="rgba(255,255,255,0.22)"
              strokeWidth="1"
            />

            {n.label === 'Patient' && (
              <g transform={`translate(${n.cx - 9}, ${n.cy - 11})`} stroke="#3BB7B2" strokeWidth="1.4" fill="none" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="9" cy="5.5" r="3.5"/>
                <path d="M1 19c0-4.4 3.6-8 8-8s8 3.6 8 8" strokeWidth="1.3"/>
              </g>
            )}

            {n.label === 'Hospital' && (
              <g transform={`translate(${n.cx - 9}, ${n.cy - 10})`} stroke="#3BB7B2" strokeWidth="1.3" fill="none" strokeLinecap="round" strokeLinejoin="round">
                <rect x="1" y="5" width="16" height="13" rx="1"/>
                <path d="M4 5V3.5a5 5 0 0110 0V5"/>
                <line x1="9" y1="8.5" x2="9" y2="13.5"/>
                <line x1="6.5" y1="11" x2="11.5" y2="11"/>
              </g>
            )}

            {n.label === 'Admin' && (
              <g transform={`translate(${n.cx - 9}, ${n.cy - 9})`} stroke="#3BB7B2" strokeWidth="1.3" fill="none" strokeLinecap="round" strokeLinejoin="round">
                <rect x="1" y="1" width="16" height="12" rx="1.5"/>
                <line x1="9" y1="13" x2="9" y2="17"/>
                <line x1="5" y1="17" x2="13" y2="17"/>
                <line x1="4" y1="5"  x2="9"  y2="5"/>
                <line x1="4" y1="8"  x2="14" y2="8"/>
                <line x1="4" y1="11" x2="11" y2="11"/>
              </g>
            )}

            <text
              x={n.cx}
              y={labelY}
              textAnchor="middle"
              dominantBaseline={n.labelDY < 0 ? 'auto' : 'hanging'}
              fontSize="9.5"
              fontWeight="600"
              fontFamily="'Source Sans 3', sans-serif"
              fill="rgba(255,255,255,0.65)"
              letterSpacing="0.02em"
            >
              {n.label}
            </text>
          </g>
        )
      })}

      <circle cx={HUB.cx} cy={HUB.cy} r={HUB.r + 8}
        fill="none" stroke="#006EB6" strokeWidth="12" opacity="0.18"/>
      <circle cx={HUB.cx} cy={HUB.cy} r={HUB.r}
        fill="#006EB6" stroke="rgba(255,255,255,0.2)" strokeWidth="1.5"/>

      <g transform={`translate(${HUB.cx - 13}, ${HUB.cy - 13})`}
        stroke="white" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round">
        <path d="M13 21.7C6 17 2 12.5 2 8.5A5.5 5.5 0 0113 6a5.5 5.5 0 0111 2.5c0 4-4 8.5-11 13.2z"/>
        <polyline points="7,12 10,9 12,14 14,8 17,12"/>
      </g>

      <text
        x={HUB.cx} y={HUB.cy + HUB.r + 11}
        textAnchor="middle"
        fontSize="8"
        fontWeight="700"
        fontFamily="'Source Sans 3', sans-serif"
        fill="rgba(255,255,255,0.4)"
        letterSpacing="0.08em"
      >
        CTS HEALTHCARE
      </text>
    </svg>
  )
}
