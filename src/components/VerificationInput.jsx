import styles from './VerificationInput.module.css'
import inputStyles from './FormInput.module.css'

/**
 * VerificationInput — OTP / verification code field.
 * Frontend UI only — resend is a stub for future backend integration.
 *
 * Props:
 *  value       {string}
 *  onChange    {function}
 *  error       {string}
 *  disabled    {boolean}
 */
function VerificationInput({ value, onChange, error, disabled }) {
  const hasError = Boolean(error)

  const handleResend = () => {
    // TODO: call POST /api/auth/resend-otp when backend is ready
    console.info('Resend verification code — backend integration pending.')
  }

  return (
    <div className={inputStyles.fieldGroup}>
      <label htmlFor="verification" className={inputStyles.label}>
        Verification
      </label>

      <div
        className={[
          inputStyles.inputWrapper,
          hasError ? inputStyles.error : '',
          disabled ? inputStyles.disabled : '',
        ]
          .filter(Boolean)
          .join(' ')}
      >
        <span className={inputStyles.iconLeft} aria-hidden="true">
          <ShieldIcon />
        </span>

        <input
          id="verification"
          type="text"
          inputMode="numeric"
          maxLength={8}
          placeholder="Enter verification code"
          value={value}
          onChange={onChange}
          disabled={disabled}
          autoComplete="one-time-code"
          aria-invalid={hasError}
          aria-describedby={hasError ? 'verification-error' : 'verification-hint'}
          className={inputStyles.input}
          spellCheck={false}
        />
      </div>

      {hasError ? (
        <p id="verification-error" className={inputStyles.errorMsg} role="alert" aria-live="polite">
          <ErrorIcon />
          {error}
        </p>
      ) : (
        <p id="verification-hint" className={styles.hint}>
          Didn&apos;t receive the code?{' '}
          <button
            type="button"
            className={styles.resendBtn}
            onClick={handleResend}
            disabled
            aria-disabled="true"
            title="Resend will be available once backend is connected"
          >
            Resend
          </button>
        </p>
      )}
    </div>
  )
}

function ShieldIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
      <path d="M7.5 1.5L2 3.5V7.5c0 2.8 2.2 5.2 5.5 6 3.3-.8 5.5-3.2 5.5-6V3.5L7.5 1.5z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
      <path d="M5 7.5l1.5 1.5 3-3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
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

export default VerificationInput
