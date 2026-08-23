import styles from './Footer.module.css'

export default function Footer() {
  return (
    <footer className={styles.footer} role="contentinfo">
      <div className={styles.inner}>
        <div className={styles.brand}>
          <div className={styles.logoRow}>
            <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
              <rect width="22" height="22" rx="4" fill="#006EB6"/>
              <rect x="8.5" y="3"  width="5" height="16" rx="1.25" fill="white"/>
              <rect x="3"   y="8.5" width="16" height="5"  rx="1.25" fill="white"/>
            </svg>
            <span className={styles.logoName}>CTS Healthcare</span>
          </div>
          <p className={styles.tagline}>Connected Healthcare Platform</p>
        </div>

        <div className={styles.links}>
          <div className={styles.group}>
            <span className={styles.groupLabel}>Platform</span>
            <span className={styles.link}>About</span>
            <span className={styles.link}>How It Works</span>
            <span className={styles.link}>Security</span>
          </div>
          <div className={styles.group}>
            <span className={styles.groupLabel}>Access</span>
            <span className={styles.link}>Patient</span>
            <span className={styles.link}>Hospital</span>
            <span className={styles.link}>Administration</span>
          </div>
        </div>
      </div>

      <div className={styles.bar}>
        <span>© 2026 CTS Healthcare. All rights reserved.</span>
        <span className={styles.note}>Frontend prototype — backend integration pending.</span>
      </div>
    </footer>
  )
}
