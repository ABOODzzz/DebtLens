import { Link } from "wouter";
import { buttonVariants } from "@/components/ui/button";
import { useLanguage } from "@/lib/i18n/context";

export default function NotFound() {
  const { t } = useLanguage();
  return (
    <div className="flex-1 flex flex-col items-center justify-center p-4 text-center">
      <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center mb-6">
        <span className="text-3xl font-bold text-primary">404</span>
      </div>
      <h1 className="text-2xl font-bold text-primary mb-2">{t('notFound.title')}</h1>
      <p className="text-muted-foreground mb-8 max-w-md">
        {t('notFound.body')}
      </p>
      <Link href="/" className={buttonVariants({ size: "lg", className: "bg-primary text-primary-foreground hover:bg-primary/90" })}>
        {t('notFound.backHome')}
      </Link>
    </div>
  );
}
