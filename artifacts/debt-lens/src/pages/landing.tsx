import React from "react";
import { useGetHeadlines } from "@workspace/api-client-react";
import { Link } from "wouter";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ShieldCheck, PieChart, ArrowRightLeft, Sparkles, Building, LineChart, ChevronLeft } from "lucide-react";
import { useLanguage } from "@/lib/i18n/context";

export default function LandingPage() {
  const { t } = useLanguage();
  return (
    <div className="flex flex-col min-h-screen">
      <NewsTicker />
      
      {/* Hero Section */}
      <section className="relative bg-primary overflow-hidden border-b border-primary/20">
        <div className="absolute inset-0 bg-[url('https://images.unsplash.com/photo-1556742049-0cfed4f6a45d?q=80&w=2070')] bg-cover bg-center opacity-10 mix-blend-overlay"></div>
        <div className="absolute inset-0 bg-gradient-to-t from-primary to-transparent"></div>
        
        <div className="container mx-auto px-4 py-24 md:py-32 relative z-10 flex flex-col items-center text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-secondary/20 text-secondary mb-6 border border-secondary/30 backdrop-blur-sm">
            <ShieldCheck className="w-4 h-4" />
            <span className="text-sm font-medium">{t('landing.hero.badge')}</span>
          </div>
          
          <h1 className="text-4xl md:text-6xl font-bold text-primary-foreground leading-tight max-w-4xl mb-6">
            {t('landing.hero.title')} <span className="text-secondary">{t('landing.hero.titleHighlight')}</span>
          </h1>
          
          <p className="text-lg md:text-xl text-primary-foreground/80 max-w-2xl mb-10 leading-relaxed">
            {t('landing.hero.subtitle')}
          </p>
          
          <div className="flex flex-col sm:flex-row gap-4 w-full sm:w-auto">
            <Link href="/register" className={buttonVariants({ size: "lg", className: "w-full sm:w-auto bg-secondary text-secondary-foreground hover:bg-secondary/90 text-lg px-8 h-14" })}>
              {t('landing.hero.startCta')}
            </Link>
            <Link href="/login" className={buttonVariants({ size: "lg", variant: "outline", className: "w-full sm:w-auto text-lg px-8 h-14 bg-white/5 border-white/20 text-white hover:bg-white/10" })}>
              {t('landing.hero.loginCta')}
            </Link>
          </div>
        </div>
      </section>

      {/* About Section */}
      <section className="py-20 bg-background">
        <div className="container mx-auto px-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-12 items-center">
            <div className="space-y-6">
              <h2 className="text-3xl md:text-4xl font-bold text-primary">{t('landing.about.title')}</h2>
              <p className="text-muted-foreground text-lg leading-relaxed">
                {t('landing.about.body')}
              </p>
              <ul className="space-y-4">
                {[
                  t('landing.about.points.point1'),
                  t('landing.about.points.point2'),
                  t('landing.about.points.point3'),
                ].map((item, i) => (
                  <li key={i} className="flex items-start gap-3">
                    <div className="w-6 h-6 rounded-full bg-secondary/20 flex items-center justify-center shrink-0 mt-0.5">
                      <CheckIcon className="w-4 h-4 text-secondary" />
                    </div>
                    <span className="text-foreground font-medium">{item}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="relative">
              <div className="aspect-square md:aspect-auto md:h-[500px] rounded-2xl overflow-hidden shadow-2xl border-4 border-white">
                <img 
                  src="https://images.unsplash.com/photo-1600880292203-757bb62b4baf?q=80&w=2070" 
                  alt="Financial Planning" 
                  className="w-full h-full object-cover"
                />
              </div>
              <div className="absolute -bottom-6 -left-6 bg-card p-6 rounded-xl shadow-xl border border-border max-w-[250px] animate-bounce-slow">
                <div className="flex items-center gap-4 mb-2">
                  <div className="w-10 h-10 rounded-full bg-green-100 flex items-center justify-center text-green-600">
                    <ArrowRightLeft className="w-5 h-5" />
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">{t('landing.about.badgeLabel')}</p>
                    <p className="font-bold text-primary">{t('landing.about.badgeValue')}</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Services Section */}
      <section className="py-20 bg-muted/30 border-t border-border">
        <div className="container mx-auto px-4">
          <div className="text-center max-w-3xl mx-auto mb-16">
            <h2 className="text-3xl font-bold text-primary mb-4">{t('landing.services.title')}</h2>
            <p className="text-muted-foreground text-lg">
              {t('landing.services.subtitle')}
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <LandingServiceCard 
              icon={<PieChart />}
              title={t('landing.services.analysis.title')}
              desc={t('landing.services.analysis.desc')}
            />
            <LandingServiceCard 
              icon={<Sparkles />}
              title={t('landing.services.advice.title')}
              desc={t('landing.services.advice.desc')}
            />
            <LandingServiceCard 
              icon={<ArrowRightLeft />}
              title={t('landing.services.restructure.title')}
              desc={t('landing.services.restructure.desc')}
            />
            <LandingServiceCard 
              icon={<Building />}
              title={t('landing.services.consolidation.title')}
              desc={t('landing.services.consolidation.desc')}
            />
            <LandingServiceCard 
              icon={<LineChart />}
              title={t('landing.services.eligibility.title')}
              desc={t('landing.services.eligibility.desc')}
            />
          </div>
        </div>
      </section>
    </div>
  );
}

function NewsTicker() {
  const { data: headlines, isLoading } = useGetHeadlines();
  const { t } = useLanguage();

  if (isLoading || !headlines || headlines.length === 0) return null;

  return (
    <div className="bg-primary border-b border-primary/20 text-primary-foreground/90 py-2 overflow-hidden flex items-center shadow-inner relative z-20">
      <div className="container mx-auto flex items-center">
        <div className="shrink-0 bg-secondary text-secondary-foreground text-xs font-bold px-3 py-1 rounded-sm ml-4 z-10 shadow-sm relative">
          {t('landing.ticker.label')}
          {/* Arrow pointing left */}
          <div className="absolute top-1/2 -left-2 -translate-y-1/2 border-8 border-transparent border-r-secondary"></div>
        </div>
        <div className="flex-1 overflow-hidden relative h-6">
          <div className="whitespace-nowrap absolute top-0 animate-ticker inline-block">
            {headlines.map((item, i) => (
              <span key={item.id} className="mx-8 text-sm">
                <span className="opacity-60 text-xs ml-2">[{item.source}]</span>
                {item.text}
              </span>
            ))}
            {/* Duplicate for seamless loop */}
            {headlines.map((item, i) => (
              <span key={`dup-${item.id}`} className="mx-8 text-sm">
                <span className="opacity-60 text-xs ml-2">[{item.source}]</span>
                {item.text}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function LandingServiceCard({ icon, title, desc }: { icon: React.ReactNode, title: string, desc: string }) {
  const { t } = useLanguage();
  return (
    <Link href="/login">
      <Card className="group cursor-pointer hover:border-secondary transition-all hover:shadow-xl bg-card border-border h-full flex flex-col relative overflow-hidden">
        <div className="absolute top-0 right-0 w-32 h-32 bg-secondary/5 rounded-bl-full -z-10 group-hover:scale-110 transition-transform"></div>
        <CardContent className="p-8 flex flex-col h-full z-10">
          <div className="w-14 h-14 rounded-2xl bg-primary/5 flex items-center justify-center text-primary group-hover:bg-secondary group-hover:text-secondary-foreground transition-colors mb-6 shadow-sm">
            {React.cloneElement(icon as React.ReactElement<any>, { className: "w-7 h-7" })}
          </div>
          <h3 className="text-xl font-bold text-primary mb-3">{title}</h3>
          <p className="text-muted-foreground leading-relaxed flex-1">{desc}</p>
          
          <div className="mt-6 flex items-center text-sm font-semibold text-primary group-hover:text-secondary transition-colors">
            {t('landing.services.browse')}
            <ChevronLeft className="w-4 h-4 mr-1 transition-transform group-hover:-translate-x-1" />
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

function CheckIcon(props: any) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}
