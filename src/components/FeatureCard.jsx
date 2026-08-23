import styles from './FeatureCard.module.css'

/**
 * FeatureCard — capability card on landing page.
 * Props: icon (Lucide element), title, description
 */
export default function FeatureCard({ icon, title, description }) {
  return (
    <div className={styles.card}>
      <div className={styles.iconWrap} aria-hidden="true">{icon}</div>
      <h3 className={styles.title}>{title}</h3>
      <p className={styles.desc}>{description}</p>
    </div>
  )
}
