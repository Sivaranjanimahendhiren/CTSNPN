import { Shield, Hospital, User, Monitor, LogOut, CheckCircle, Clock } from 'lucide-react'
import styles from './Dashboard.module.css'

const PORTAL_META = {
  patient:  { label: 'Patient Portal',  icon: <User size={16} />,     color: '#006EB6', bg: '#E8F3FB', border: '#C9D3DA' },
  hospital: { label: 'Hospital Portal', icon: <Hospital size={16} />, color: '#008C95', bg: '#E6F5F6', border: '#B2E0E2' },
  cms:      { label: 'Admin Portal',    icon: <Monitor size={16} />,  color: '#17365D', bg: '#E9EFF2', border: '#C9D3DA' },
}

/**
 * Dashboard — post-login placeholder screen.
 * Shows session info and a logout button.
 * Uses official brand colors and clean Lucide icons.
 *
 * Props:
 *  session  { type, name, email?, memberId?, orgName?, adminId?, loginTime }
 *  onLogout {function}
 */
export default function Dashboard({ session, onLogout }) {
  if (!session) return null
  const meta = PORTAL_META[session.type] || PORTAL_META.patient
  const loginDate = new Date(session.loginTime).toLocaleString()

  return (
    <div className={styles.page}>
      {/* Top bar */}
      <header className={styles.topBar}>
        <div className={styles.logoRow}>
          <svg width="26" height="26" viewBox="0 0 26 26" fill="none" aria-hidden="true">
            <rect width="26" height="26" rx="6" fill="#006EB6"/>
            <rect x="10" y="4"  width="6" height="18" rx="1.5" fill="white"/>
            <rect x="4"  y="10" width="18" height="6"  rx="1.5" fill="white"/>
          </svg>
          <span className={styles.logoText}>CTS Healthcare</span>
        </div>

        <div className={styles.sessionInfo}>
          <span className={styles.portalBadge} style={{ color: meta.color, backgroundColor: meta.bg, borderColor: meta.border }}>
            <span style={{ display: 'inline-flex', marginRight: '4px', verticalAlign: 'middle' }}>{meta.icon}</span>
            {meta.label}
          </span>
          <span className={styles.userName}>{session.name}</span>
        </div>

        <button className={styles.logoutBtn} onClick={onLogout} aria-label="Sign out">
          <LogOut size={14} />
          Sign Out
        </button>
      </header>

      {/* Main content */}
      <main className={styles.main}>
        {/* Welcome card */}
        <div className={styles.welcomeCard}>
          <div className={styles.welcomeIcon} aria-hidden="true">
            {session.type === 'patient' && <User size={40} strokeWidth={1.5} />}
            {session.type === 'hospital' && <Hospital size={40} strokeWidth={1.5} />}
            {session.type === 'cms' && <Monitor size={40} strokeWidth={1.5} />}
          </div>
          <div className={styles.welcomeText}>
            <h1 className={styles.welcomeHeading}>Welcome back, {session.name}</h1>
            <p className={styles.welcomeSub}>You are signed in to the secure <strong>{meta.label}</strong>.</p>
          </div>
        </div>

        {/* Session details */}
        <div className={styles.detailCard}>
          <h2 className={styles.detailHeading}>Session Information</h2>
          <div className={styles.detailGrid}>
            <DetailRow label="Portal Role" value={meta.label} />
            <DetailRow label="Account Name" value={session.name} />
            {session.email    && <DetailRow label="Email Address" value={session.email} />}
            {session.memberId && <DetailRow label="Member ID" value={session.memberId} />}
            {session.orgName  && <DetailRow label="Organization" value={session.orgName} />}
            {session.adminId  && <DetailRow label="Admin ID"  value={session.adminId} />}
            <DetailRow label="Authentication Time" value={loginDate} />
          </div>
        </div>

        {/* Placeholder content */}
        <div className={styles.placeholderCard}>
          <h2 className={styles.placeholderHeading}>{meta.label} Demonstration</h2>
          <p className={styles.placeholderText}>
            This portal is operating in local demonstration mode. Session authentication, route protection,
            and state verification are active. Full database connections and services will be enabled upon Fast API integration.
          </p>
          <div className={styles.techStatus}>
            <span className={styles.statusBadgeActive}>
              <CheckCircle size={10} style={{ marginRight: '4px', display: 'inline-block' }} />
              Session Verified
            </span>
            <span className={styles.statusBadgePending}>
              <Clock size={10} style={{ marginRight: '4px', display: 'inline-block' }} />
              Service Integration Pending
            </span>
          </div>
        </div>
      </main>

      <footer className={styles.footer}>
        © 2026 CTS Healthcare. All rights reserved.
      </footer>
    </div>
  )
}

function DetailRow({ label, value }) {
  return (
    <div className={styles.detailRow}>
      <span className={styles.detailLabel}>{label}</span>
      <span className={styles.detailValue}>{value}</span>
    </div>
  )
}
