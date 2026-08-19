import { useState } from 'react'
import { ChevronLeft, CheckCircle, Hospital, CreditCard, Mail, Phone, MapPin, AlertCircle, ShieldCheck } from 'lucide-react'
import FormInput from '../components/FormInput'
import PasswordInput from '../components/PasswordInput'
import styles from './Registration.module.css'

const INITIAL = {
  orgName: '', regId: '', email: '', mobile: '',
  address: '', password: '', confirmPassword: '',
}
const INIT_ERR = { ...INITIAL }

const VALIDATORS = {
  orgName:         v => !v.trim() ? 'Organization name is required.' : '',
  regId:           v => !v.trim() ? 'Hospital Registration ID is required.' : '',
  email:           v => !v.trim() ? 'Official email is required.' : !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) ? 'Enter a valid email address.' : '',
  mobile:          v => !v.trim() ? 'Official mobile number is required.' : v.replace(/\D/g,'').length < 7 ? 'Enter a valid mobile number.' : '',
  address:         v => !v.trim() ? 'Organization address is required.' : '',
  password:        v => !v        ? 'Password is required.' : v.length < 8 ? 'Password must be at least 8 characters.' : '',
  confirmPassword: (v, all) => !v ? 'Please confirm your password.' : v !== all.password ? 'Passwords do not match.' : '',
}

/**
 * HospitalRegistration
 * Props:
 *  onBack     {function}
 *  onRegister {function(data) → { ok, error }}
 */
export default function HospitalRegistration({ onBack, onRegister }) {
  const [fields, setFields]   = useState(INITIAL)
  const [errors, setErrors]   = useState(INIT_ERR)
  const [isLoading, setIsLoading]   = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [success, setSuccess] = useState(false)

  const handle = (field) => (e) => {
    const value = e.target.value
    setFields(prev => ({ ...prev, [field]: value }))
    if (errors[field]) {
      const merged = { ...fields, [field]: value }
      const msg = field === 'confirmPassword'
        ? VALIDATORS.confirmPassword(value, merged)
        : VALIDATORS[field]?.(value) ?? ''
      setErrors(prev => ({ ...prev, [field]: msg }))
    }
  }

  const validate = () => {
    const updated = { ...INIT_ERR }
    let valid = true
    Object.keys(VALIDATORS).forEach(f => {
      const msg = f === 'confirmPassword'
        ? VALIDATORS.confirmPassword(fields[f], fields)
        : VALIDATORS[f]?.(fields[f]) ?? ''
      if (msg) { updated[f] = msg; valid = false }
    })
    setErrors(updated)
    return valid
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSubmitError('')
    if (!validate()) return

    setIsLoading(true)
    await new Promise(r => setTimeout(r, 800))

    const result = onRegister?.({
      orgName:  fields.orgName,
      regId:    fields.regId,
      email:    fields.email,
      mobile:   fields.mobile,
      address:  fields.address,
      password: fields.password,
    }) ?? { ok: true }

    if (result.ok) {
      setSuccess(true)
    } else {
      setSubmitError(result.error)
    }
    setIsLoading(false)
  }

  /* ---- Success screen ---- */
  if (success) {
    return (
      <div className={styles.page}>
        <div className={styles.successCard}>
          <CheckCircle size={52} className={styles.successIcon} aria-hidden="true" />
          <h2 className={styles.successHeading}>Hospital Registered!</h2>
          <p className={styles.successText}>
            Your hospital has been successfully registered. You can now sign in to
            CTS Healthcare using your <strong>Organization Name</strong> and password.
          </p>
          <div className={styles.successDetail}>
            <span className={styles.successDetailLabel}>Organization</span>
            <span className={styles.successDetailValue}>{fields.orgName}</span>
          </div>
          <button className={styles.backBtn} onClick={onBack}>Sign In Now</button>
        </div>
      </div>
    )
  }

  /* ---- Registration form ---- */
  return (
    <div className={styles.page}>
      <div className={styles.container}>
        <div className={styles.topBar}>
          <button className={styles.back} onClick={onBack} aria-label="Back to sign in">
            <ChevronLeft size={16} /> Back to Sign In
          </button>
        </div>

        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <span className={styles.badge}>Hospital Registration</span>
            <h1 className={styles.heading}>Register Your Hospital</h1>
            <p className={styles.subheading}>
              Create an organization account to manage your hospital on CTS Healthcare.
            </p>
          </div>

          {submitError && (
            <div className={styles.errBanner} role="alert" aria-live="assertive">
              <AlertCircle size={15} /> {submitError}
            </div>
          )}

          <form onSubmit={handleSubmit} noValidate>
            <div className={styles.fields}>
              {/* Organization Information */}
              <div className={styles.sectionGroup}>
                <h3 className={styles.sectionLabel}>Organization Information</h3>
                <div className={styles.row}>
                  <FormInput id="orgName" label="Organization Name"        placeholder="Enter your organization name"   value={fields.orgName} onChange={handle('orgName')} error={errors.orgName} disabled={isLoading} autoComplete="organization" icon={<Hospital size={16} />} />
                  <FormInput id="regId"   label="Hospital Registration ID" placeholder="Enter hospital registration ID"  value={fields.regId}   onChange={handle('regId')}   error={errors.regId}   disabled={isLoading} autoComplete="off"          icon={<CreditCard size={16} />} />
                </div>
              </div>

              {/* Contact Information */}
              <div className={styles.sectionGroup}>
                <h3 className={styles.sectionLabel}>Contact Information</h3>
                <div className={styles.row}>
                  <FormInput id="hosp-email"  label="Official Email"         placeholder="Enter official email"          value={fields.email}  onChange={handle('email')}  error={errors.email}  disabled={isLoading} type="email" autoComplete="email" icon={<Mail size={16} />} />
                  <FormInput id="hosp-mobile" label="Official Mobile Number" placeholder="Enter official mobile number"  value={fields.mobile} onChange={handle('mobile')} error={errors.mobile} disabled={isLoading} inputMode="tel" autoComplete="tel" prefix="+91" />
                </div>
                <FormInput id="address" label="Organization Address" placeholder="Enter full organization address" value={fields.address} onChange={handle('address')} error={errors.address} disabled={isLoading} autoComplete="street-address" icon={<MapPin size={16} />} />
              </div>

              {/* Security */}
              <div className={styles.sectionGroup}>
                <h3 className={styles.sectionLabel}>Security</h3>
                <div className={styles.row}>
                  <PasswordInput id="hosp-password" label="Password"         placeholder="Create a secure password (min. 8 chars)" value={fields.password}        onChange={handle('password')}        error={errors.password}        disabled={isLoading} autoComplete="new-password" />
                  <PasswordInput id="hosp-confirm"  label="Confirm Password" placeholder="Confirm your password"                    value={fields.confirmPassword} onChange={handle('confirmPassword')} error={errors.confirmPassword} disabled={isLoading} autoComplete="new-password" />
                </div>
              </div>
            </div>

            <button type="submit" className={styles.submitBtn} disabled={isLoading}>
              {isLoading
                ? <><span className={styles.spinner} aria-hidden="true" />Registering…</>
                : 'Register Hospital'
              }
            </button>
          </form>

          <p className={styles.secMsg}>
            Secure access for authorized hospital personnel.
          </p>
        </div>

        <footer className={styles.footer}>© 2026 CTS Healthcare. All rights reserved.</footer>
      </div>
    </div>
  )
}
