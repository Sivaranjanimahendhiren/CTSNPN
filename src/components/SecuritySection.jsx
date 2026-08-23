import { ShieldCheck, LockKeyhole, UserCheck, HeartPulse, CheckCircle } from 'lucide-react'
import styles from './SecuritySection.module.css'

const ITEMS = [
  {
    icon: <ShieldCheck size={18} strokeWidth={1.75} />,
    label: 'Secure Access',
    desc: 'Multi-layer authentication and session management for all user types.',
  },
  {
    icon: <LockKeyhole size={18} strokeWidth={1.75} />,
    label: 'Protected Information',
    desc: 'Healthcare data handled with responsible access controls and privacy practices.',
  },
  {
    icon: <UserCheck size={18} strokeWidth={1.75} />,
    label: 'Controlled Access',
    desc: 'Role-based access ensures each user sees only what is relevant to them.',
  },
  {
    icon: <HeartPulse size={18} strokeWidth={1.75} />,
    label: 'Healthcare Focus',
    desc: 'Designed specifically for the clinical and administrative healthcare environment.',
  },
]

export default function SecuritySection() {
  return (
    <section id="security" className={styles.section} aria-labelledby="sec-heading">
      <div className={styles.inner}>

        {/* Text column */}
        <div className={styles.text}>
          <p className={styles.tag}>Security &amp; Trust</p>
          <h2 id="sec-heading" className={styles.heading}>Built for Trusted Healthcare Access</h2>
          <p className={styles.sub}>
            Designed with secure access, controlled experiences, and responsible
            healthcare information management in mind.
          </p>

          <ul className={styles.list} aria-label="Security features">
            {ITEMS.map(item => (
              <li key={item.label} className={styles.listItem}>
                <span className={styles.itemIcon} aria-hidden="true">{item.icon}</span>
                <div>
                  <span className={styles.itemLabel}>{item.label}</span>
                  <span className={styles.itemDesc}>{item.desc}</span>
                </div>
              </li>
            ))}
          </ul>
        </div>

        {/* Right column — clean summary panel */}
        <div className={styles.panel} aria-hidden="true">
          <div className={styles.panelHeader}>
            <CheckCircle size={20} strokeWidth={1.75} className={styles.panelIcon} />
            <span className={styles.panelTitle}>Platform Security</span>
          </div>
          <div className={styles.panelItems}>
            {['Secure Authentication', 'Role-Based Access', 'Session Management', 'Data Privacy Controls', 'Audit Trails'].map(item => (
              <div key={item} className={styles.panelItem}>
                <div className={styles.panelDot} />
                <span>{item}</span>
              </div>
            ))}
          </div>
          <div className={styles.panelNote}>
            Designed for clinical, hospital, and government healthcare environments.
          </div>
        </div>

      </div>
    </section>
  )
}
