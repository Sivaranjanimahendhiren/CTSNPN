/**
 * PageLoader — ultra-thin top progress bar for page transitions.
 * Replaces the full-screen overlay. Appears only for ~400ms.
 *
 * Props:
 *  visible {boolean}
 */
import styles from './PageLoader.module.css'

export default function PageLoader({ visible }) {
  if (!visible) return null
  return (
    <div
      className={styles.bar}
      role="status"
      aria-label="Navigating"
      aria-live="polite"
    >
      <div className={styles.fill} aria-hidden="true" />
    </div>
  )
}
