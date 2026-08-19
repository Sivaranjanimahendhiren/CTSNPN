import { useState, useCallback } from 'react'
import { useAuth } from './hooks/useAuth'
import SplashScreen from './components/SplashScreen'
import PageLoader   from './components/PageLoader'
import LandingPage         from './pages/LandingPage'
import LoginPage           from './pages/LoginPage'
import PatientRegistration from './pages/PatientRegistration'
import HospitalRegistration from './pages/HospitalRegistration'
import Dashboard           from './pages/Dashboard'

/**
 * App — root router with splash screen and page transition loader.
 * Views: 'landing' | 'login' | 'patient-register' | 'hospital-register' | 'dashboard'
 */
export default function App() {
  const [splashDone, setSplashDone]   = useState(false)
  const [view, setView]               = useState('landing')
  const [loading, setLoading]         = useState(false)
  const { session, login, logout, registerPatient, registerHospital } = useAuth()

  /* Navigate with a short loader transition */
  const navigate = useCallback((target) => {
    setLoading(true)
    setTimeout(() => {
      setView(target)
      setLoading(false)
    }, 450)
  }, [])

  /* Restore session */
  if (splashDone && session && (view === 'landing' || view === 'login')) {
    return (
      <>
        <PageLoader visible={loading} />
        <Dashboard session={session} onLogout={() => { logout(); navigate('landing') }} />
      </>
    )
  }

  /* Show splash first */
  if (!splashDone) {
    return <SplashScreen onComplete={() => setSplashDone(true)} />
  }

  /* Page routing */
  const renderPage = () => {
    switch (view) {
      case 'login':
        return (
          <LoginPage
            onLogin={(credentials, rememberMe) => {
              const result = login(credentials, rememberMe)
              if (result.ok) navigate('dashboard')
              return result
            }}
            onPatientRegister={() => navigate('patient-register')}
            onHospitalRegister={() => navigate('hospital-register')}
            onBack={() => navigate('landing')}
          />
        )
      case 'patient-register':
        return (
          <PatientRegistration
            onBack={() => navigate('login')}
            onRegister={(data) => registerPatient(data)}
          />
        )
      case 'hospital-register':
        return (
          <HospitalRegistration
            onBack={() => navigate('login')}
            onRegister={(data) => registerHospital(data)}
          />
        )
      case 'dashboard':
        return (
          <Dashboard
            session={session}
            onLogout={() => { logout(); navigate('landing') }}
          />
        )
      default:
        return <LandingPage onGetStarted={() => navigate('login')} />
    }
  }

  return (
    <>
      <PageLoader visible={loading} />
      {renderPage()}
    </>
  )
}
