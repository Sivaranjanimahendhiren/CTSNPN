import styles from './HowItWorks.module.css'

const STEPS = [
  {
    num: '01',
    title: 'Access',
    desc: 'Securely access the CTS Healthcare platform using your registered credentials.',
  },
  {
    num: '02',
    title: 'Connect',
    desc: 'Your account connects you to the services and information relevant to your role.',
  },
  {
    num: '03',
    title: 'Manage',
    desc: 'Use the healthcare tools and information available to you through your account.',
  },
]

export default function HowItWorks() {
  return (
    <section id="how-it-works" className={styles.section} aria-labelledby="hiw-heading">
      <div className={styles.inner}>
        <div className={styles.hdr}>
          <p className={styles.tag}>Process</p>
          <h2 id="hiw-heading" className={styles.heading}>How Care Connects</h2>
          <p className={styles.sub}>Three steps to access the CTS Healthcare platform.</p>
        </div>

        <ol className={styles.steps} aria-label="Steps to access CTS Healthcare">
          {STEPS.map((s, i) => (
            <li key={s.num} className={styles.step}>
              {/* Connector line — hidden for first item on mobile */}
              {i > 0 && <div className={styles.connector} aria-hidden="true" />}

              <div className={styles.stepContent}>
                <div className={styles.num} aria-hidden="true">{s.num}</div>
                <h3 className={styles.stepTitle}>{s.title}</h3>
                <p className={styles.stepDesc}>{s.desc}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}
