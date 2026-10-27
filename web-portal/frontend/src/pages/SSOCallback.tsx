import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { homeFor } from '../utils/homePath';

export default function SSOCallbackPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { handleSsoCallback } = useAuth();
  const [statusMessage, setStatusMessage] = useState('Completing university sign in…');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const processedRef = useRef(false);

  useEffect(() => {
    if (processedRef.current) return;
    processedRef.current = true;

    const oauthError = searchParams.get('error');
    if (oauthError) {
      const desc = searchParams.get('error_description') || oauthError;
      setErrorMessage(desc);
      return;
    }

    const code = searchParams.get('code');
    if (!code) {
      setErrorMessage('No authorization code was received from the university SSO.');
      return;
    }

    const exchange = async () => {
      try {
        setStatusMessage('Exchanging authorization credentials…');
        const callbackUri = `${window.location.origin}/auth/callback`;
        const loggedIn = await handleSsoCallback(code, callbackUri);
        setStatusMessage('Sign-in successful! Redirecting…');
        navigate(homeFor(loggedIn.role), { replace: true });
      } catch (err: unknown) {
        let msg = 'University SSO authentication failed.';
        if (typeof err === 'object' && err !== null && 'response' in err) {
          const resp = (err as { response?: { data?: { error?: { message?: string } } } }).response;
          if (resp?.data?.error?.message) {
            msg = resp.data.error.message;
          }
        }
        setErrorMessage(msg);
      }
    };

    void exchange();
  }, [searchParams, handleSsoCallback, navigate]);

  return (
    <div className="flex min-h-screen w-full items-center justify-center bg-[#0a0a0a] text-white p-6">
      <div className="flex max-w-md w-full flex-col items-center gap-4 rounded-xl border border-white/10 bg-[#121212] p-8 text-center shadow-2xl">
        {errorMessage ? (
          <>
            <div className="h-12 w-12 rounded-full bg-red-500/10 flex items-center justify-center text-red-400">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h2 className="text-lg font-semibold text-red-400">Authentication Failed</h2>
            <p className="text-sm text-white/70">{errorMessage}</p>
            <button
              type="button"
              onClick={() => navigate('/login', { replace: true })}
              className="mt-4 w-full rounded-lg bg-white px-4 py-2.5 text-sm font-medium text-black hover:bg-white/90 transition-colors"
            >
              Back to Sign in
            </button>
          </>
        ) : (
          <>
            <div className="h-10 w-10 animate-spin rounded-full border-2 border-white/20 border-t-white" />
            <h2 className="text-base font-medium text-white">{statusMessage}</h2>
            <p className="text-xs text-white/50">Please wait while your session is verified.</p>
          </>
        )}
      </div>
    </div>
  );
}

