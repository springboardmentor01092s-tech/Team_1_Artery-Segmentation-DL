import { useAuth } from '../context/AuthContext';
import { ErrorState } from './ui';

export default function SessionRecovery() {
  const { restorationError, retrySession, dismissSession } = useAuth();
  return <main className="card" style={{ maxWidth: 680, margin: '10vh auto', padding: 24 }}>
    <h1>Session verification unavailable</h1>
    <ErrorState error={restorationError} retry={retrySession} />
    <p>No protected information is loaded until your session is verified.</p>
    <button className="btn btn-ghost" onClick={dismissSession}>Sign out on this device</button>
  </main>;
}
