import { ReactNode } from 'react';
import { useAuth } from '@/lib/auth-context';
import { Link, useLocation } from 'wouter';
import { LogOut, User, ShieldCheck, Languages } from 'lucide-react';
import { auth } from '@/lib/firebase';
import { signOut } from 'firebase/auth';
import { buttonVariants, Button } from './ui/button';
import { NotificationBell } from './notification-bell';
import { useLanguage } from '@/lib/i18n/context';

export function Layout({ children }: { children: ReactNode }) {
  const { user, isAdmin } = useAuth();
  const [location] = useLocation();
  const { t, dir, toggleLanguage, language } = useLanguage();

  const handleLogout = async () => {
    await signOut(auth);
  };

  return (
    <div className="min-h-[100dvh] flex flex-col bg-background" dir={dir}>
      {/* Header */}
      <header className="sticky top-0 z-50 w-full border-b border-border bg-white/80 backdrop-blur-md">
        <div className="container mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Link href="/" className="flex items-center gap-2">
              <div className="w-8 h-8 rounded bg-primary flex items-center justify-center text-secondary font-bold text-lg">
                D
              </div>
              <span className="font-bold text-xl text-primary tracking-tight">
                Debt<span className="text-secondary">Lens</span>
              </span>
            </Link>
          </div>

          <nav className="flex items-center gap-4">
            {user ? (
              <>
                {isAdmin ? (
                  <Link href="/admin" className="text-sm font-medium text-muted-foreground hover:text-primary transition-colors flex items-center gap-1">
                    <ShieldCheck className="w-4 h-4" /> {t('common.nav.admin')}
                  </Link>
                ) : (
                  <Link href="/dashboard" className="text-sm font-medium text-muted-foreground hover:text-primary transition-colors flex items-center gap-1">
                    <User className="w-4 h-4" /> {t('common.nav.dashboard')}
                  </Link>
                )}
                {!isAdmin && <NotificationBell />}
                <Button variant="ghost" size="sm" onClick={handleLogout} className="text-muted-foreground hover:text-destructive gap-2">
                  <LogOut className="w-4 h-4" />
                  {t('common.nav.logout')}
                </Button>
              </>
            ) : (
              <>
                <Link href="/login" className={buttonVariants({ variant: "ghost", size: "sm" })}>
                  {t('common.nav.login')}
                </Link>
                <Link href="/register" className={buttonVariants({ variant: "default", size: "sm", className: "bg-secondary text-secondary-foreground hover:bg-secondary/90" })}>
                  {t('common.nav.register')}
                </Link>
              </>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={toggleLanguage}
              className="gap-1.5 font-semibold"
              aria-label={t('common.languageSwitcher.srLabel')}
              data-testid="button-language-switcher"
            >
              <Languages className="w-4 h-4" />
              {t('common.languageSwitcher.label')}
            </Button>
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex flex-col">
        {children}
      </main>

      {/* Footer */}
      <footer className="border-t border-border bg-card py-8 mt-auto">
        <div className="container mx-auto px-4 text-center text-sm text-muted-foreground">
          <p>{t('common.footer.rights')} &copy; {new Date().getFullYear()} DebtLens</p>
          <p className="mt-2 text-xs">{t('common.footer.tagline')}</p>
        </div>
      </footer>
    </div>
  );
}
