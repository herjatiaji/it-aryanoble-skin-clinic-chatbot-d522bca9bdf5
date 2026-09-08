import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

export default function Login() {
  const [doctors, setDoctors] = useState([])
  const [selectedDoctor, setSelectedDoctor] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    fetch('/api/doctors')
      .then(res => res.json())
      .then(data => {
        setDoctors(data)
        if (data.length > 0) setSelectedDoctor(data[0].cis_id)
      })
      .catch(err => console.error('Failed to fetch doctors', err))
  }, [])

  const handleLogin = async (e) => {
    e.preventDefault()
    try {
      const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cis_id: selectedDoctor })
      })
      if (res.ok) {
        const data = await res.json()
        localStorage.setItem('cis_token', data.access_token)
        localStorage.setItem('cis_doctor', JSON.stringify(data.doctor))
        navigate('/dashboard')
      } else {
        alert('Login failed')
      }
    } catch (err) {
      console.error(err)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', marginTop: '100px', fontFamily: 'sans-serif' }}>
      <h2>CIS External System (Mock)</h2>
      <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '1rem', width: '300px', marginTop: '20px' }}>
        <label>Select Mock Doctor:</label>
        <select value={selectedDoctor} onChange={e => setSelectedDoctor(e.target.value)} style={{ padding: '8px', fontSize: '16px' }}>
          {doctors.map(doc => (
            <option key={doc.cis_id} value={doc.cis_id}>
              {doc.name}
            </option>
          ))}
        </select>
        <button type="submit" style={{ padding: '10px', background: '#0070f3', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '16px' }}>
          Login to CIS Dashboard
        </button>
      </form>
    </div>
  )
}
