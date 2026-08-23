import styles from './CTASection.module.css'

export default function CTASection({ onGetStarted }) {
  return (
    <section id="contact" className={styles.section} aria-labelledby="cta-heading">
      <div className={styles.inner}>
        <h2 id="cta-heading" className={styles.heading}>Ready to Get Started?</h2>
        <p className={styles.sub}>
          Access your CTS Healthcare experience through one secure, unified platform.
        </p>
        <button className={styles.btn} onClick={onGetStarted}>
          Sign In to CTS Healthcare
        </button>
      </div>
    </section>
  )
}
