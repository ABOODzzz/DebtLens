import { type ReactNode, useEffect } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ErrorBoundary } from '@/components/error-boundary';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import { Route, Switch, useLocation, Router as WouterRouter } from 'wouter';
import { AuthProvider, useAuth } from '@/lib/auth-context';
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

function ProtectedRoute({ component: Component, adminOnly = false }: { component: React.ComponentType, adminOnly?: boolean }) {
  const { user, loading, isAdmin, profile } = useAuth();
  const [_, setLocation] = useLocation();

  useEffect(() => {
    if (!loading) {
      if (!user) {
        setLocation('/login');
      } else if (adminOnly && !isAdmin) {
        setLocation('/dashboard');
      } else if (!adminOnly && !isAdmin && profile && !profile.profileCompleted) {
        setLocation('/wizard');
      }
    }
  }, [user, loading, isAdmin, profile, adminOnly, setLocation]);

  if (loading) return <LoadingScreen />;
  if (!user) return null;
  if (adminOnly && !isAdmin) return null;
  if (!adminOnly && !isAdmin && profile && !profile.profileCompleted) return null;

  return <Component />;
}

function WizardRoute({ component: Component }: { component: React.ComponentType }) {
  const { user, loading, profile, isAdmin } = useAuth();
  const [_, setLocation] = useLocation();

  useEffect(() => {
    if (!loading) {
      if (!user) {
        setLocation('/login');
      } else if (isAdmin) {
        setLocation('/admin');
      } else if (profile?.profileCompleted) {
        setLocation('/dashboard');
      }
    }
  }, [user, loading, profile, isAdmin, setLocation]);

  if (loading) return <LoadingScreen />;
  if (!user || isAdmin || profile?.profileCompleted) return null;

  return <Component />;
}

function PublicOnlyRoute({ component: Component }: { component: React.ComponentType }) {
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

function Router() {
  return (
    <Layout>
      <Switch>
        <Route path="/" component={LandingPage} />
        <Route path="/login">
          <PublicOnlyRoute component={LoginPage} />
        </Route>
        <Route path="/register">
          <PublicOnlyRoute component={RegisterPage} />
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
    </QueryClientProvider>
  );
}

export default App;
