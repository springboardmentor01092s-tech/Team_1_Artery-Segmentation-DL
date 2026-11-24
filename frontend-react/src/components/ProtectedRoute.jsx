import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Loading } from './ui';
import SessionRecovery from './SessionRecovery';

export default function ProtectedRoute({ children, roles }) {
  const { user, loading, restorationError } = useAuth();
  const location = useLocation();
  if (loading) return <Loading label="Verifying your session..." />;
  if (restorationError) return <SessionRecovery />;
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/403" replace />;
  return children;
}
