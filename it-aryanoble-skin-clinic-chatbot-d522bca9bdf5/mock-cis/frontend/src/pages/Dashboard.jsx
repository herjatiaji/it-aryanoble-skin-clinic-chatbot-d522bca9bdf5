import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import FloatingChatbot from '../components/FloatingChatbot'

export default function Dashboard() {
  const navigate = useNavigate()
  const [doctor, setDoctor] = useState(null)

  useEffect(() => {
    const token = localStorage.getItem('cis_token')
    const docData = localStorage.getItem('cis_doctor')
    if (!token || !docData) {
      navigate('/')
    } else {
      setDoctor(JSON.parse(docData))
    }
  }, [navigate])

  const handleLogout = () => {
    localStorage.removeItem('cis_token')
    localStorage.removeItem('cis_doctor')
    navigate('/')
  }

  if (!doctor) return null

  return (
    <div style={{ 
      minHeight: '100vh', 
      backgroundColor: '#f4f4f5', 
      display: 'flex', 
      flexDirection: 'column', 
      alignItems: 'center', 
      justifyContent: 'center', 
      padding: '2rem',
      fontFamily: 'sans-serif'
    }}>
      <div style={{ textAlign: 'center', maxWidth: '32rem', marginBottom: '2rem' }}>
        <h1 style={{ fontSize: '1.25rem', fontWeight: 'bold', color: '#18181b', margin: '0 0 0.5rem 0' }}>
          External CIS Dashboard (Mock)
        </h1>
        <p style={{ color: '#52525b', fontSize: '0.875rem', marginBottom: '1rem' }}>
          Logged in as: {doctor.name}
        </p>
        <button 
          onClick={handleLogout}
          style={{ padding: '8px 16px', background: '#ef4444', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '14px' }}>
          Logout
        </button>
      </div>
      
      {/* Floating Chatbot Component */}
      <FloatingChatbot 
        token={localStorage.getItem('cis_token')}
        doctorName={doctor ? doctor.name : 'Unknown'}
        branchId="11111111-1111-1111-1111-111111111111" // In a real app, this would be fetched from context or state
        apiBaseUrl="http://localhost:8000"
      />
    </div>
  )
}
