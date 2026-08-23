import { useState } from 'react'
import { ChevronLeft, CheckCircle, User, CreditCard, Phone, Mail, Calendar, AlertCircle } from 'lucide-react'
import FormInput from '../components/FormInput'
import PasswordInput from '../components/PasswordInput'
import styles from './Registration.module.css'

const INIT = { fullName:'', memberId:'', mobile:'', email:'', dob:'', password:'', confirmPassword:'' }
const V = {
  fullName:        v => !v.trim()  ? 'Full name is required.' : '',
  memberId:        v => !v.trim()  ? 'Member ID is required.' : '',
  mobile:          v => !v.trim()  ? 'Mobile number is required.' : v.replace(/\D/g,'').length < 7 ? 'Enter a valid mobile number.' : '',
  email:           v => !v.trim()  ? 'Email address is required.' : !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) ? 'Enter a valid email.' : '',
  dob:             v => !v         ? 'Date of birth is required.' : '',
  password:        v => !v         ? 'Password is required.' : v.length < 8 ? 'Minimum 8 characters.' : '',
  confirmPassword: (v,a) => !v     ? 'Please confirm your password.' : v !== a.password ? 'Passwords do not match.' : '',
}

export default function PatientRegistration({ onBack, onRegister }) {
  const [f, setF] = useState(INIT)
  const [e, setE] = useState(INIT)
  const [loading, setLoading] = useState(false)
  const [submitErr, setSubmitErr] = useState('')
  const [done, setDone] = useState(false)

  const h = (field) => (ev) => {
    const v = ev.target.value
    setF(p => ({ ...p, [field]: v }))
    if (e[field]) setE(p => ({ ...p, [field]: field === 'confirmPassword' ? V.confirmPassword(v, { ...f, [field]: v }) : V[field]?.(v) ?? '' }))
  }

  const validate = () => {
    const errs = { ...INIT }
    let ok = true
    Object.keys(V).forEach(k => {
      const msg = k === 'confirmPassword' ? V.confirmPassword(f[k], f) : V[k]?.(f[k]) ?? ''
      if (msg) { errs[k] = msg; ok = false }
    })
    setE(errs)
    return ok
  }

  const submit = async (ev) => {
    ev.preventDefault()
    setSubmitErr('')
    if (!validate()) return
    setLoading(true)
    await new Promise(r => setTimeout(r, 800))
    const res = onRegister?.({ fullName:f.fullName, memberId:f.memberId, mobile:f.mobile, email:f.email, dob:f.dob, password:f.password }) ?? { ok:true }
    if (res.ok) setDone(true)
    else setSubmitErr(res.error)
    setLoading(false)
  }

  if (done) return (
    <div className={styles.page}>
      <div className={styles.successCard}>
        <CheckCircle size={52} className={styles.successIcon}/>
        <h2 className={styles.successHeading}>Account Created</h2>
        <p className={styles.successText}>Your patient account has been created. Sign in using your Member ID and password.</p>
        <div className={styles.successDetail}>
          <span className={styles.successDetailLabel}>Member ID</span>
          <span className={styles.successDetailValue}>{f.memberId}</span>
        </div>
        <button className={styles.backBtn} onClick={onBack}>Sign In Now</button>
      </div>
    </div>
  )

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        <div className={styles.topBar}>
          <button className={styles.back} onClick={onBack}><ChevronLeft size={16}/> Back to Sign In</button>
        </div>
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <span className={styles.badge}>Patient Registration</span>
            <h1 className={styles.heading}>Create Patient Account</h1>
            <p className={styles.subheading}>Register to access your personal healthcare information on CTS Healthcare.</p>
          </div>

          {submitErr && <div className={styles.errBanner}><AlertCircle size={15}/> {submitErr}</div>}

          <form onSubmit={submit} noValidate>
            <div className={styles.fields}>
              {/* Personal Information Group */}
              <div className={styles.sectionGroup}>
                <h3 className={styles.sectionLabel}>Personal Information</h3>
                <div className={styles.row}>
                  <FormInput id="pt-name"   label="Full Name"     placeholder="Enter your full name"   value={f.fullName} onChange={h('fullName')} error={e.fullName} disabled={loading} autoComplete="name"     icon={<User     size={16}/>}/>
                  <FormInput id="pt-mid"    label="Member ID"     placeholder="Enter your Member ID"   value={f.memberId} onChange={h('memberId')} error={e.memberId} disabled={loading} autoComplete="username" icon={<CreditCard size={16}/>}/>
                </div>
                <div className={styles.rowThird}>
                  <FormInput id="pt-dob"   label="Date of Birth" placeholder="" value={f.dob} onChange={h('dob')} error={e.dob} disabled={loading} type="date" autoComplete="bday" icon={<Calendar size={16}/>}/>
                </div>
              </div>

              {/* Contact Information Group */}
              <div className={styles.sectionGroup}>
                <h3 className={styles.sectionLabel}>Contact Information</h3>
                <div className={styles.row}>
                  <FormInput id="pt-mob"    label="Mobile Number" placeholder="Enter your mobile number" value={f.mobile} onChange={h('mobile')} error={e.mobile} disabled={loading} inputMode="tel" autoComplete="tel" prefix="+91"/>
                  <FormInput id="pt-email"  label="Email Address" placeholder="Enter your email address" value={f.email}  onChange={h('email')}  error={e.email}  disabled={loading} type="email" autoComplete="email" icon={<Mail size={16}/>}/>
                </div>
              </div>

              {/* Security Group */}
              <div className={styles.sectionGroup}>
                <h3 className={styles.sectionLabel}>Security</h3>
                <div className={styles.row}>
                  <PasswordInput id="pt-pass"  label="Password"         placeholder="Create a password (min. 8 chars)" value={f.password}        onChange={h('password')}        error={e.password}        disabled={loading} autoComplete="new-password"/>
                  <PasswordInput id="pt-conf"  label="Confirm Password" placeholder="Confirm your password"             value={f.confirmPassword} onChange={h('confirmPassword')} error={e.confirmPassword} disabled={loading} autoComplete="new-password"/>
                </div>
              </div>
            </div>
            <button type="submit" className={styles.submitBtn} disabled={loading}>
              {loading ? <><span className={styles.spinner}/>Creating Account…</> : 'Create Account'}
            </button>
          </form>
          <p className={styles.secMsg}>Secure healthcare access — your information is protected.</p>
        </div>
        <footer className={styles.footer}>© 2026 CTS Healthcare. All rights reserved.</footer>
      </div>
    </div>
  )
}
