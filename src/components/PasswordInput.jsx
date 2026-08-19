import { useState } from 'react'
import styles from './FormInput.module.css'
import pwStyles from './PasswordInput.module.css'

/**
 * PasswordInput — password field with show/hide toggle.
 *
 * Props:
 *  id          {string}
 *  label       {string}
 *  placeholder {string}
 *  value       {string}
 *  onChange    {function}
 *  error       {string}
 *  disabled    {boolean}
 *  autoComplete{string}
 */
function PasswordInput({ id = 'password', label = 'Password', placeholder, value, onChange, error, disabled, autoComplete = 'current-password' }) {
  const [visible, setVisible] = useState(false)
  const hasError = Boolean(error)

  return (
    <div className={styles.fieldGroup}>
      <label htmlFor={id} className={styles.label}>
        {label}
      </label>

      <div
        className={[
          styles.inputWrapper,
          hasError ? styles.error : '',
          disabled ? styles.disabled : '',
        ]
          .filter(Boolean)
          .join(' ')}
      >
        {/* Lock icon */}
        <span className={styles.iconLeft} aria-hidden="true">
          <LockIcon />
        </span>

        <input
          id={id}
          type={visible ? 'text' : 'password'}
          placeholder={placeholder || 'Enter your password'}
          value={value}
          onChange={onChange}
          disabled={disabled}
          autoComplete={autoComplete}
          aria-invalid={hasError}
          aria-describedby={hasError ? `${id}-error` : undefined}
          className={styles.input}
        />

        <button
          type="button"
          className={pwStyles.eyeBtn}
          onClick={() => setVisible(v => !v)}
          disabled={disabled}
          aria-label={visible ? 'Hide password' : 'Show password'}
        >
          {visible ? <EyeOffIcon /> : <EyeIcon />}
        </button>
      </div>

      {hasError && (
        <p id={`${id}-error`} className={styles.errorMsg} role="alert" aria-live="polite">
          <ErrorIcon />
          {error}
        </p>
      )}
    </div>
  )
}

/* ---- Icons ---- */
function LockIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
      <rect x="2.5" y="6.5" width="10" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.2" />
      <path d="M4.5 6.5V5a3 3 0 016 0v1.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
      <circle cx="7.5" cy="10" r="1" fill="currentColor" />
    </svg>
  )
}

function EyeIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 17 17" fill="none" aria-hidden="true">
      <path d="M1.5 8.5C1.5 8.5 4 3.5 8.5 3.5S15.5 8.5 15.5 8.5 13 13.5 8.5 13.5 1.5 8.5 1.5 8.5z" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="8.5" cy="8.5" r="2" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  )
}

function EyeOffIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 17 17" fill="none" aria-hidden="true">
      <path d="M2 2L15 15" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
      <path d="M7.2 3.7A7 7 0 018.5 3.5c4.5 0 7 5 7 5a13 13 0 01-2 2.8" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
      <path d="M5.1 5.1A6.8 6.8 0 001.5 8.5S4 13.5 8.5 13.5a6.8 6.8 0 004.4-1.6" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
      <path d="M6.5 6.5a2 2 0 002.9 2.9" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  )
}

function ErrorIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true">
      <circle cx="6.5" cy="6.5" r="5.75" stroke="currentColor" strokeWidth="1.1" />
      <path d="M6.5 3.75v3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
      <circle cx="6.5" cy="9.25" r="0.7" fill="currentColor" />
    </svg>
  )
}

export default PasswordInput
