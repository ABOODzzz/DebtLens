import { type ReactNode, useEffect } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ErrorBoundary } from '@/components/error-boundary';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import { Route, Switch, useLocation, Router as WouterRouter } from 'wouter';
import { AuthProvider, useAuth } from '@/lib/auth-context';
import { LanguageProvider } from '@/lib/i18n/context';
import { Layout } from '@/components/layout';
import { LoadingScreen } from '@/components/ui/loading-screen';

// Pages
import LandingPage from '@/pages/landing';
import LoginPage from '@/pages/login';
import RegisterPage from '@/pages/register';
import DashboardPage from '@/pages/dashboard';
import WizardPage from '@/pages/wizard';
import AdminPage from '@/pages/admin';
import NotFound from '@/pages/not-found';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

// Login is intentionally decoupled from the profile-completion wizard: the
// wizard only ever runs once, right after account creation. An existing
// user who logs in -- complete profile or not -- always lands on their
// destination (dashboard/admin) directly, never bounced back to the wizard.
function ProtectedRoute({ component: Component, adminOnly = false }: { component: React.ComponentType, adminOnly?: boolean }) {
  const { user, loading, isAdmin } = useAuth();
  const [_, setLocation] = useLocation();

  useEffect(() => {
    if (!loading) {
      if (!user) {
        setLocation('/login');
      } else if (adminOnly && !isAdmin) {
        setLocation('/dashboard');
      }
    }
  }, [user, loading, isAdmin, adminOnly, setLocation]);

  if (loading) return <LoadingScreen />;
  if (!user) return null;
  if (adminOnly && !isAdmin) return null;

  return <Component />;
}

function WizardRoute({ component: Component }: { component: React.ComponentType }) {
  const { user, loading, profile, isAdmin } = useAuth();
  const [_, setLocation] = useLocation();

  // A rejected customer must be able to re-enter the wizard to fix and
  // resubmit their info, even though their profile was already marked
  // complete the first time through.
  const canReenterForResubmission = profile?.reviewStatus === 'rejected';
  const blockedByCompletion = !!profile?.profileCompleted && !canReenterForResubmission;

  useEffect(() => {
    if (!loading) {
      if (!user) {
        setLocation('/login');
      } else if (isAdmin) {
        setLocation('/admin');
      } else if (blockedByCompletion) {
        setLocation('/dashboard');
      }
    }
  }, [user, loading, blockedByCompletion, isAdmin, setLocation]);

  if (loading) return <LoadingScreen />;
  if (!user || isAdmin || blockedByCompletion) return null;

  return <Component />;
}

// /login is a pure sign-in page: an already-authenticated visitor -- and
// crucially, anyone who just typed a registered email/password here --
// always lands on their dashboard/admin directly. Login never routes
// through the profile-completion wizard, no matter how far that account
// got through onboarding.
function LoginRoute({ component: Component }: { component: React.ComponentType }) {
  const { user, loading, isAdmin } = useAuth();
  const [_, setLocation] = useLocation();

  useEffect(() => {
    if (!loading && user) {
      setLocation(isAdmin ? '/admin' : '/dashboard');
    }
  }, [user, loading, isAdmin, setLocation]);

  if (loading) return <LoadingScreen />;
  if (user) return null;

  return <Component />;
}

// /register is the only entry point into the onboarding wizard: right
// after account creation the profile is incomplete, so this sends the
// brand-new user into /wizard. An already-complete profile that somehow
// lands back on /register (e.g. a stale tab) is sent to the dashboard
// instead of back through onboarding.
function RegisterRoute({ component: Component }: { component: React.ComponentType }) {
  const { user, loading, isAdmin, profile } = useAuth();
  const [_, setLocation] = useLocation();

  useEffect(() => {
    if (!loading && user) {
      if (isAdmin) {
        setLocation('/admin');
      } else if (profile && !profile.profileCompleted) {
        setLocation('/wizard');
      } else if (profile) {
        setLocation('/dashboard');
      }
      // profile === null (still being created/loaded right after signup):
      // wait for the next snapshot rather than guessing a destination.
    }
  }, [user, loading, isAdmin, profile, setLocation]);

  if (loading) return <LoadingScreen />;
  if (user) return null;

  return <Component />;
}

function Router() {
  return (
    <Layout>
      <Switch>
        <Route path="/" component={LandingPage} />
        <Route path="/login">
          <LoginRoute component={LoginPage} />
        </Route>
        <Route path="/register">
          <RegisterRoute component={RegisterPage} />
        </Route>
        <Route path="/wizard">
          <WizardRoute component={WizardPage} />
        </Route>
        <Route path="/dashboard">
          <ProtectedRoute component={DashboardPage} />
        </Route>
        <Route path="/admin">
          <ProtectedRoute component={AdminPage} adminOnly />
        </Route>
        <Route component={NotFound} />
      </Switch>
    </Layout>
  );
}

function RoutedErrorBoundary({ children }: { children: ReactNode }) {
  const [location] = useLocation();
  return <ErrorBoundary resetKey={location}>{children}</ErrorBoundary>;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <LanguageProvider>
        <AuthProvider>
          <TooltipProvider>
            <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}>
              <RoutedErrorBoundary>
                <Router />
              </RoutedErrorBoundary>
            </WouterRouter>
            <Toaster />
          </TooltipProvider>
        </AuthProvider>
      </LanguageProvider>
    </QueryClientProvider>
  );
}

export default App;
