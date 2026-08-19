/**
 * FormInput — universal single-line input field.
 *
 * Props:
 *  id          {string}   — links <label> to <input>
 *  label       {string}   — visible label text
 *  type        {string}   — input type (default: 'text')
 *  placeholder {string}
 *  value       {string}
 *  onChange    {function}
 *  error       {string}   — inline error message; empty = no error
 *  disabled    {boolean}
 *  autoComplete{string}
 *  prefix      {node}     — optional left prefix element (e.g. country code)
 *  icon        {node}     — optional left SVG icon
 *  inputMode   {string}   — e.g. 'numeric', 'tel'
 *  maxLength   {number}
 */
import styles from './FormInput.module.css'

function FormInput({
  id,
  label,
  type = 'text',
  placeholder,
  value,
  onChange,
  error,
  disabled,
  autoComplete,
  prefix,
  icon,
  inputMode,
  maxLength,
}) {
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
        {icon && (
          <span className={styles.iconLeft} aria-hidden="true">
            {icon}
          </span>
        )}

        {prefix && (
          <span className={styles.prefix} aria-hidden="true">
            {prefix}
          </span>
        )}

        <input
          id={id}
          type={type}
          placeholder={placeholder}
          value={value}
          onChange={onChange}
          disabled={disabled}
          autoComplete={autoComplete}
          aria-invalid={hasError}
          aria-describedby={hasError ? `${id}-error` : undefined}
          inputMode={inputMode}
          maxLength={maxLength}
          className={[styles.input, prefix ? styles.inputWithPrefix : ''].filter(Boolean).join(' ')}
          spellCheck={false}
        />
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

function ErrorIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true">
      <circle cx="6.5" cy="6.5" r="5.75" stroke="currentColor" strokeWidth="1.1" />
      <path d="M6.5 3.75v3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
      <circle cx="6.5" cy="9.25" r="0.7" fill="currentColor" />
    </svg>
  )
}

export default FormInput
