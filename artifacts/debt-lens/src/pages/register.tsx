import { useState } from "react";
import { Link } from "wouter";
import { createUserWithEmailAndPassword } from "firebase/auth";
import { doc, setDoc } from "firebase/firestore";
import { auth, db } from "@/lib/firebase";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { ShieldCheck, Mail, Lock, Loader2, User } from "lucide-react";
import { useLanguage } from "@/lib/i18n/context";

export default function RegisterPage() {
  const { t } = useLanguage();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const userCredential = await createUserWithEmailAndPassword(auth, email, password);
      const user = userCredential.user;
      
      // Initialize the user document
      await setDoc(doc(db, "users", user.uid), {
        fullName: name,
        profileCompleted: false,
        createdAt: new Date().toISOString(),
      });
      
      // App.tsx will handle the redirect to /wizard
    } catch (err: any) {
      if (err.code === 'auth/email-already-in-use') {
        setError(t('register.errorEmailInUse'));
      } else if (err.code === 'auth/weak-password') {
        setError(t('register.errorWeakPassword'));
      } else {
        setError(t('register.errorGeneric'));
      }
      setLoading(false);
    }
  };

  return (
    <div className="flex-1 flex items-center justify-center bg-background p-4 relative overflow-hidden">
      {/* Decorative background elements */}
      <div className="absolute top-[-10%] right-[-10%] w-96 h-96 bg-secondary/10 rounded-full blur-3xl" />
      <div className="absolute bottom-[-10%] left-[-10%] w-96 h-96 bg-primary/5 rounded-full blur-3xl" />

      <Card className="w-full max-w-md glass-card z-10 animate-in fade-in slide-in-from-bottom-4 duration-500">
        <CardHeader className="text-center space-y-4">
          <div className="w-12 h-12 rounded-full bg-secondary/20 flex items-center justify-center mx-auto text-secondary">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <div className="space-y-1">
            <CardTitle className="text-2xl font-bold text-primary">{t('register.title')}</CardTitle>
            <CardDescription>{t('register.subtitle')}</CardDescription>
          </div>
        </CardHeader>
        <form onSubmit={handleSubmit}>
          <CardContent className="space-y-4">
            {error && (
              <div className="p-3 text-sm bg-destructive/10 text-destructive border border-destructive/20 rounded-md">
                {error}
              </div>
            )}
            
            <div className="space-y-2">
              <Label htmlFor="name">{t('register.nameLabel')}</Label>
              <div className="relative">
                <User className="absolute right-3 top-3 h-4 w-4 text-muted-foreground" />
                <Input
                  id="name"
                  type="text"
                  placeholder={t('register.namePlaceholder')}
                  className="pr-10"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="email">{t('register.emailLabel')}</Label>
              <div className="relative">
                <Mail className="absolute right-3 top-3 h-4 w-4 text-muted-foreground" />
                <Input
                  id="email"
                  type="email"
                  placeholder="name@example.com"
                  className="pr-10 dir-ltr text-left"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">{t('register.passwordLabel')}</Label>
              <div className="relative">
                <Lock className="absolute right-3 top-3 h-4 w-4 text-muted-foreground" />
                <Input
                  id="password"
                  type="password"
                  className="pr-10 dir-ltr text-left"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={6}
                />
              </div>
              <p className="text-xs text-muted-foreground">{t('register.passwordHint')}</p>
            </div>
          </CardContent>
          <CardFooter className="flex flex-col space-y-4">
            <Button type="submit" className="w-full bg-secondary text-secondary-foreground hover:bg-secondary/90" disabled={loading}>
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : t('register.submit')}
            </Button>
            <div className="text-sm text-center text-muted-foreground">
              {t('register.haveAccount')} <Link href="/login" className="text-primary font-semibold hover:underline">{t('register.login')}</Link>
            </div>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}
