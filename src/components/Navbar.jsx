import { useState } from 'react'
import { Menu, X } from 'lucide-react'
import styles from './Navbar.module.css'

export default function Navbar({ onSignIn }) {
  const [open, setOpen] = useState(false)
  const go = (id) => { setOpen(false); document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' }) }

  return (
    <header className={styles.header} role="banner">
      <div className={styles.inner}>
        {/* Logo */}
        <button className={styles.logo} onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })} aria-label="CTS Healthcare — top">
          <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
            <rect width="28" height="28" rx="5" fill="#006EB6"/>
            <rect x="11" y="3"  width="6" height="22" rx="1.5" fill="white"/>
            <rect x="3"  y="11" width="22" height="6"  rx="1.5" fill="white"/>
          </svg>
          <div className={styles.logoText}>
            <span className={styles.logoName}>CTS Healthcare</span>
            <span className={styles.logoSub}>Connected Healthcare Platform</span>
          </div>
        </button>

        {/* Desktop nav */}
        <nav className={styles.nav} aria-label="Main navigation">
          <button className={styles.link} onClick={() => go('about')}>About</button>
          <button className={styles.link} onClick={() => go('how-it-works')}>How It Works</button>
          <button className={styles.link} onClick={() => go('security')}>Security</button>
        </nav>

        <button className={styles.signIn} onClick={onSignIn}>Sign In</button>

        {/* Mobile toggle */}
        <button className={styles.toggle} onClick={() => setOpen(o => !o)}
          aria-label={open ? 'Close menu' : 'Open menu'} aria-expanded={open}>
          {open ? <X size={20}/> : <Menu size={20}/>}
        </button>
      </div>

      {/* Mobile drawer */}
      {open && (
        <nav className={styles.drawer} aria-label="Mobile navigation">
          <button className={styles.drawerLink} onClick={() => go('about')}>About</button>
          <button className={styles.drawerLink} onClick={() => go('how-it-works')}>How It Works</button>
          <button className={styles.drawerLink} onClick={() => go('security')}>Security</button>
          <button className={styles.drawerSignIn} onClick={() => { setOpen(false); onSignIn() }}>Sign In</button>
        </nav>
      )}
    </header>
  )
}
