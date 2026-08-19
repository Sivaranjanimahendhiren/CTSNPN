import { useEffect, useState } from 'react'
import { HeartPulse } from 'lucide-react'
import styles from './SplashScreen.module.css'

/**
 * SplashScreen — enterprise-grade initial load screen.
 * Displays for ~1400ms then calls onComplete.
 * Deliberately minimal: single icon, name, subtitle, thin loader.
 *
 * Props:
 *  onComplete {function} — called when splash finishes
 */
export default function SplashScreen({ onComplete }) {
  const [phase, setPhase] = useState(0)
  // 0 = blank  1 = icon  2 = name  3 = subtitle  4 = loading  5 = fade out

  useEffect(() => {
    const timers = [
      setTimeout(() => setPhase(1), 150),
      setTimeout(() => setPhase(2), 320),
      setTimeout(() => setPhase(3), 500),
      setTimeout(() => setPhase(4), 700),
      setTimeout(() => setPhase(5), 1300),
      setTimeout(() => onComplete?.(), 1600),
    ]
    return () => timers.forEach(clearTimeout)
  }, [onComplete])

  const v = (n) => phase >= n ? styles.visible : ''

  return (
    <div
      className={[styles.splash, phase === 5 ? styles.fadeOut : ''].filter(Boolean).join(' ')}
      role="status"
      aria-label="CTS Healthcare loading"
      aria-live="polite"
    >
      <div className={styles.center}>

        {/* Single centered icon */}
        <div className={[styles.iconWrap, v(1)].filter(Boolean).join(' ')} aria-hidden="true">
          <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
            <rect width="28" height="28" rx="6" fill="rgba(255,255,255,0.12)"/>
            <rect x="11" y="3"  width="6" height="22" rx="1.5" fill="white"/>
            <rect x="3"  y="11" width="22" height="6"  rx="1.5" fill="white"/>
          </svg>
          <HeartPulse size={22} strokeWidth={1.75} />
        </div>

        {/* Brand name */}
        <div className={[styles.brandName, v(2)].filter(Boolean).join(' ')}>
          CTS Healthcare
        </div>

        {/* Subtitle */}
        <div className={[styles.subtitle, v(3)].filter(Boolean).join(' ')}>
          Connected Healthcare Platform
        </div>

        {/* Thin loading bar */}
        <div className={[styles.loadingBar, v(4)].filter(Boolean).join(' ')} aria-label="Loading">
          <div className={styles.loadingFill} />
        </div>

      </div>
    </div>
  )
}
