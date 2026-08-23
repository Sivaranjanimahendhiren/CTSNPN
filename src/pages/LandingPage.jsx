import { UserRound, Hospital, LayoutDashboard } from 'lucide-react'
import Navbar from '../components/Navbar'
import Hero from '../components/Hero'
import FeatureCard from '../components/FeatureCard'
import HowItWorks from '../components/HowItWorks'
import SecuritySection from '../components/SecuritySection'
import CTASection from '../components/CTASection'
import Footer from '../components/Footer'
import styles from './LandingPage.module.css'

const CAPABILITIES = [
  {
    icon: <UserRound size={26} strokeWidth={1.75}/>,
    title: 'Patient Care',
    description: 'Access personal healthcare information and services through a secure digital experience.',
  },
  {
    icon: <Hospital size={26} strokeWidth={1.75}/>,
    title: 'Hospital Operations',
    description: 'Manage patients, healthcare records, and hospital operations efficiently.',
  },
  {
    icon: <LayoutDashboard size={26} strokeWidth={1.75}/>,
    title: 'Healthcare Management',
    description: 'Monitor healthcare operations and analyze system-level information through centralized management tools.',
  },
]

export default function LandingPage({ onGetStarted }) {
  return (
    <div className={styles.page}>
      <Navbar onSignIn={onGetStarted} />

      <main>
        <Hero onGetStarted={onGetStarted} />

        {/* Capabilities */}
        <section id="capabilities" className={styles.capSection} aria-labelledby="cap-heading">
          <div id="about" className={styles.anchor} aria-hidden="true"/>
          <div className={styles.capInner}>
            <div className={styles.capHeader}>
              <p className={styles.capTag}>Platform Capabilities</p>
              <h2 id="cap-heading" className={styles.capHeading}>
                One Platform. Connected Healthcare.
              </h2>
              <p className={styles.capSub}>
                Designed to bring patients, hospitals, and healthcare management together
                through a unified digital experience.
              </p>
            </div>
            <div className={styles.capGrid} role="list">
              {CAPABILITIES.map(c => (
                <div key={c.title} role="listitem" className={styles.capItem}>
                  <FeatureCard icon={c.icon} title={c.title} description={c.description}/>
                </div>
              ))}
            </div>
          </div>
        </section>

        <HowItWorks />
        <SecuritySection />
        <CTASection onGetStarted={onGetStarted}/>
      </main>

      <Footer />
    </div>
  )
}
