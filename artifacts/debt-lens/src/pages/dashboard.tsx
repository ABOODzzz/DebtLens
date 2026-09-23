import { useGetFinancialSummary, useAnalyzeFinances, useGetRestructurePlan, useGetAdvice, useRequestConsolidation, useAssessLoanEligibility, useGetGuarantorStatus, GuarantorStatus } from "@workspace/api-client-react";
import { useAuth } from "@/lib/auth-context";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { AlertCircle, LineChart, PieChart, Sparkles, Building, ArrowRightLeft, Loader2, CheckCircle2, ShieldAlert, ShieldCheck, Users } from "lucide-react";
import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";

export default function DashboardPage() {
  const { profile } = useAuth();
  
  // Status check
  if (profile?.reviewStatus === "pending") {
    return (
      <div className="flex-1 container mx-auto p-4 md:p-8 max-w-3xl flex items-center justify-center">
        <Card className="glass-card text-center py-16 px-8 w-full border-secondary/20">
          <Loader2 className="w-16 h-16 animate-spin text-secondary mx-auto mb-6" />
          <h2 className="text-2xl font-bold text-primary mb-2">جاري مراجعة ملفك</h2>
          <p className="text-muted-foreground">يقوم خبراؤنا بمراجعة مستنداتك وبياناتك المالية. هذه العملية تستغرق وقتاً قصيراً لضمان تقديم أفضل الاستشارات المخصصة لك.</p>
        </Card>
      </div>
    );
  }

  if (profile?.reviewStatus === "rejected") {
    return (
      <div className="flex-1 container mx-auto p-4 md:p-8 max-w-3xl flex items-center justify-center">
        <Card className="border-destructive/20 text-center py-16 px-8 w-full bg-destructive/5">
          <ShieldAlert className="w-16 h-16 text-destructive mx-auto mb-6" />
          <h2 className="text-2xl font-bold text-destructive mb-2">تم رفض الملف</h2>
          <p className="text-muted-foreground mb-4">السبب: {profile.reviewReason || "المستندات غير مطابقة للشروط"}</p>
          <Button variant="outline" onClick={() => window.location.href="/wizard"}>إعادة التقديم</Button>
        </Card>
      </div>
    );
  }

  // Dashboard for approved users
  return <DashboardContent />;
}

function DashboardContent() {
  const { profile } = useAuth();
  const summaryQuery = useGetFinancialSummary();
  const guarantorQuery = useGetGuarantorStatus();
  const [activeDialog, setActiveDialog] = useState<string | null>(null);

  if (summaryQuery.isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-secondary" />
      </div>
    );
  }

  if (summaryQuery.isError || !summaryQuery.data) {
    return (
      <div className="p-8 text-center text-destructive">
        <AlertCircle className="w-12 h-12 mx-auto mb-4" />
        <p>حدث خطأ أثناء تحميل بياناتك المالية.</p>
      </div>
    );
  }

  const summary = summaryQuery.data;
  const isVerified = summary.dataSource === "verified";

  return (
    <div className="flex-1 bg-muted/10 pb-12">
      {/* Top Banner */}
      <div className="bg-primary text-primary-foreground py-10 px-4 md:px-8 border-b-4 border-secondary">
        <div className="container mx-auto max-w-6xl flex flex-col md:flex-row items-center justify-between gap-6">
          <div>
            <h1 className="text-3xl font-bold mb-2">أهلاً بك، {profile?.fullName?.split(' ')[0] || 'عميلنا العزيز'}</h1>
            <p className="text-primary-foreground/80">إليك ملخص وضعك المالي بناءً على البيانات المقدمة.</p>
          </div>
          <div className="bg-primary-foreground/10 px-6 py-4 rounded-xl backdrop-blur-sm border border-primary-foreground/20 text-center min-w-[200px]">
            <p className="text-sm opacity-80 mb-1">إجمالي الديون المتبقية</p>
            <p className="text-3xl font-bold text-secondary">{summary.totalRemainingDebt.toLocaleString()} <span className="text-lg">د.أ</span></p>
          </div>
        </div>
      </div>

      <div className="container mx-auto max-w-6xl px-4 mt-8 space-y-8">

        {!isVerified && (
          <div className="flex items-start gap-3 bg-secondary/10 border border-secondary/30 rounded-lg p-4 text-sm">
            <AlertCircle className="w-5 h-5 text-secondary flex-shrink-0 mt-0.5" />
            <p className="text-muted-foreground">
              الأرقام أدناه مبنية على بياناتك المُدخلة عند التسجيل فقط. ستظهر أرقام دقيقة بعد رفع كشوفات حساباتك أو قروضك ومراجعتها.
            </p>
          </div>
        )}

        {/* KPI Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiCard title="الدخل الشهري" value={summary.totalMonthlyIncome} unit="د.أ" />
          <KpiCard title="الالتزامات الشهرية" value={summary.totalMonthlyDebtPayments} unit="د.أ" highlight={summary.totalMonthlyDebtPayments > summary.totalMonthlyIncome * 0.5} />
          <KpiCard title="نسبة عبء الدين" value={Math.round(summary.debtToIncomeRatio)} unit="%" highlight={summary.debtToIncomeRatio > 50} />
          <KpiCard title="عدد القروض النشطة" value={summary.activeLoansCount} unit="" isNumber />
        </div>

        <GuarantorStatusCard
          data={guarantorQuery.data}
          isLoading={guarantorQuery.isLoading}
          isError={guarantorQuery.isError}
        />

        <h2 className="text-xl font-bold text-primary border-b pb-2">الخدمات الاستشارية المتاحة لك</h2>
        
        {/* Services Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          
          <ServiceCard 
            title="تحليل شامل للبيانات" 
            description="دراسة مفصلة لوضعك المالي وتوزيع ديونك عبر الجهات المختلفة."
            icon={<PieChart className="w-6 h-6" />}
            onClick={() => setActiveDialog('full-analysis')}
          />
          
          <ServiceCard 
            title="نصائح الذكاء الاصطناعي" 
            description="نصائح مالية مخصصة مبنية على خوارزمياتنا لتحسين تصنيفك الائتماني."
            icon={<Sparkles className="w-6 h-6 text-secondary" />}
            onClick={() => setActiveDialog('ai-advice')}
          />

          {summary.hasActiveLoans && (
            <ServiceCard 
              title="خطط إعادة الهيكلة" 
              description="سيناريوهات مقترحة لتقليل القسط الشهري وتقليص فترة السداد."
              icon={<ArrowRightLeft className="w-6 h-6" />}
              onClick={() => setActiveDialog('restructure')}
            />
          )}

          {summary.hasMultipleFinancingInstitutions && (
            <ServiceCard 
              title="طلب توحيد القروض" 
              description="جمع كافة ديونك من المؤسسات المختلفة في قرض واحد بقسط مريح."
              icon={<Building className="w-6 h-6" />}
              onClick={() => setActiveDialog('consolidation')}
            />
          )}
          
          <ServiceCard 
            title="تقييم أهلية التمويل" 
            description="فحص سريع لمدى أهليتك للحصول على تمويل إضافي دون الإضرار بوضعك المالي."
            icon={<LineChart className="w-6 h-6" />}
            onClick={() => setActiveDialog('eligibility')}
          />
        </div>
      </div>

      {/* Result Dialogs */}
      {activeDialog === 'full-analysis' && <FullAnalysisDialog onClose={() => setActiveDialog(null)} />}
      {activeDialog === 'ai-advice' && <AiAdviceDialog onClose={() => setActiveDialog(null)} />}
      {activeDialog === 'restructure' && <RestructureDialog onClose={() => setActiveDialog(null)} />}
      {activeDialog === 'consolidation' && <ConsolidationDialog onClose={() => setActiveDialog(null)} />}
      {activeDialog === 'eligibility' && <EligibilityDialog onClose={() => setActiveDialog(null)} />}
    </div>
  );
}

// --- Guarantor Status Card ---
function GuarantorStatusCard({ data, isLoading, isError }: { data?: GuarantorStatus; isLoading: boolean; isError: boolean }) {
  if (isLoading) return null;
  if (isError || !data) return null;

  const { outgoing_request, approved_guarantor_uid, incoming_requests } = data;
  const incomingList = Object.entries(incoming_requests || {});

  if (!outgoing_request && !approved_guarantor_uid && incomingList.length === 0) {
    return null;
  }

  const statusLabel = (status: string) =>
    status === 'approved' ? 'تمت الموافقة' : status === 'declined' ? 'مرفوض' : 'قيد الانتظار';

  const statusClass = (status: string) =>
    status === 'approved' ? 'bg-green-100 text-green-700' :
    status === 'declined' ? 'bg-red-100 text-red-700' :
    'bg-yellow-100 text-yellow-700';

  return (
    <Card className="border-secondary/20 bg-secondary/5">
      <CardContent className="p-6 space-y-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-secondary/20 flex items-center justify-center text-primary shrink-0">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <h3 className="font-bold text-primary">الكفيل الرقمي</h3>
            <p className="text-sm text-muted-foreground">حالة طلبات الكفالة الخاصة بك</p>
          </div>
        </div>

        {approved_guarantor_uid && (
          <div className="flex items-center justify-between p-3 bg-green-50 border border-green-200 rounded-lg text-sm">
            <span className="text-green-800 font-medium">لديك كفيل معتمد يدعم طلبك التمويلي</span>
            <span className="px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-700">معتمد</span>
          </div>
        )}

        {outgoing_request && !approved_guarantor_uid && (
          <div className="flex items-center justify-between p-3 bg-muted/30 border rounded-lg text-sm">
            <span>طلب الكفالة المُرسَل (بحد أقصى {outgoing_request.maxAmount.toLocaleString()} د.أ)</span>
            <span className={`px-2 py-1 rounded-full text-xs font-medium ${statusClass(outgoing_request.status)}`}>
              {statusLabel(outgoing_request.status)}
            </span>
          </div>
        )}

        {incomingList.length > 0 && (
          <div>
            <p className="text-sm font-medium mb-2 flex items-center gap-2">
              <Users className="w-4 h-4" /> طلبات كفالة واردة إليك
            </p>
            <div className="space-y-2">
              {incomingList.map(([requesterUid, request]) => (
                <div key={requesterUid} className="flex items-center justify-between p-3 bg-muted/30 border rounded-lg text-sm">
                  <span className="truncate dir-ltr text-xs text-muted-foreground">{requesterUid}</span>
                  <span className={`px-2 py-1 rounded-full text-xs font-medium ${statusClass(request.status)}`}>
                    {statusLabel(request.status)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// --- KPI Card Component ---
function KpiCard({ title, value, unit, isNumber = false, highlight = false }: { title: string, value: number, unit: string, isNumber?: boolean, highlight?: boolean }) {
  return (
    <Card className={`overflow-hidden transition-all ${highlight ? 'border-destructive shadow-destructive/10' : 'border-border'}`}>
      <CardContent className="p-6">
        <p className="text-sm font-medium text-muted-foreground mb-2">{title}</p>
        <p className={`text-2xl font-bold ${highlight ? 'text-destructive' : 'text-primary'}`}>
          {isNumber ? value : value.toLocaleString()} <span className="text-sm font-normal">{unit}</span>
        </p>
      </CardContent>
    </Card>
  );
}

// --- Service Card Component ---
function ServiceCard({ title, description, icon, onClick }: { title: string, description: string, icon: React.ReactNode, onClick: () => void }) {
  return (
    <Card className="group cursor-pointer hover:border-secondary transition-all hover:shadow-lg bg-card/50 hover:bg-card">
      <CardContent className="p-6 flex items-start gap-4" onClick={onClick}>
        <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center text-primary group-hover:bg-secondary/20 group-hover:scale-110 transition-all shrink-0">
          {icon}
        </div>
        <div>
          <h3 className="font-bold text-lg text-primary mb-1">{title}</h3>
          <p className="text-sm text-muted-foreground leading-relaxed">{description}</p>
        </div>
      </CardContent>
    </Card>
  );
}

// --- Dialogs (Fetching real data when opened) ---

function AwaitingVerificationNotice({ message }: { message?: string }) {
  return (
    <div className="flex flex-col items-center text-center gap-3 py-6">
      <AlertCircle className="w-10 h-10 text-secondary" />
      <p className="text-muted-foreground leading-relaxed">
        {message || "بياناتك المالية لا تزال قيد المراجعة والتحليل من قبل فريقنا. سنعلمك فور اكتمال التحليل لعرض نتائجك الدقيقة."}
      </p>
    </div>
  );
}

const DialogWrapper = ({ title, isOpen, onClose, children }: { title: string, isOpen: boolean, onClose: () => void, children: React.ReactNode }) => (
  <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
    <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto" dir="rtl">
      <DialogHeader>
        <DialogTitle className="text-xl text-primary">{title}</DialogTitle>
      </DialogHeader>
      <div className="py-4">
        {children}
      </div>
    </DialogContent>
  </Dialog>
);

function FullAnalysisDialog({ onClose }: { onClose: () => void }) {
  const analysis = useAnalyzeFinances();
  
  // Auto-fetch on mount
  useState(() => {
    analysis.mutate({ data: { type: "full" } });
  });

  return (
    <DialogWrapper title="التحليل الشامل" isOpen={true} onClose={onClose}>
      {analysis.isPending ? <Loader2 className="w-8 h-8 animate-spin mx-auto text-secondary" /> : 
       analysis.isError ? <p className="text-destructive">حدث خطأ</p> : 
       analysis.data?.awaitingVerification ? <AwaitingVerificationNotice message={analysis.data.message} /> :
       analysis.data && (
         <div className="space-y-6">
           <p className="text-lg leading-relaxed text-primary">{analysis.data.summary}</p>
           
           <div className="grid grid-cols-2 gap-4">
             <div className="p-4 bg-muted/30 rounded-lg">
               <p className="text-sm text-muted-foreground">إجمالي الدين المتبقي</p>
               <p className="text-xl font-bold">{(analysis.data.totalRemainingDebt ?? 0).toLocaleString()} د.أ</p>
             </div>
             <div className="p-4 bg-muted/30 rounded-lg">
               <p className="text-sm text-muted-foreground">نسبة العبء</p>
               <p className="text-xl font-bold text-secondary">{Math.round(analysis.data.debtToIncomeRatio ?? 0)}%</p>
             </div>
           </div>

           <div>
             <h4 className="font-bold mb-3">تفصيل الديون</h4>
             <div className="space-y-2">
               {(analysis.data.debtBreakdown ?? []).map((d, i) => (
                 <div key={i} className="flex justify-between items-center p-3 border rounded">
                   <span>{d.lenderName}</span>
                   <span className="font-bold">{d.remainingAmount.toLocaleString()} د.أ</span>
                 </div>
               ))}
             </div>
           </div>

           {(analysis.data.insights ?? []).length > 0 && (
             <div>
               <h4 className="font-bold mb-2">رؤى مالية</h4>
               <ul className="list-disc list-inside space-y-1 text-muted-foreground pr-4">
                 {(analysis.data.insights ?? []).map((insight, i) => <li key={i}>{insight}</li>)}
               </ul>
             </div>
           )}
         </div>
       )}
    </DialogWrapper>
  );
}

function AiAdviceDialog({ onClose }: { onClose: () => void }) {
  const advice = useGetAdvice();
  
  useState(() => {
    advice.mutate();
  });

  return (
    <DialogWrapper title="استشارة الذكاء الاصطناعي" isOpen={true} onClose={onClose}>
      {advice.isPending ? <Loader2 className="w-8 h-8 animate-spin mx-auto text-secondary" /> : 
       advice.isError ? <p className="text-destructive">حدث خطأ</p> : 
       advice.data?.awaitingVerification ? <AwaitingVerificationNotice message={advice.data.message} /> :
       advice.data && (
         <div className="bg-primary/5 p-6 rounded-xl border border-primary/10">
           <div className="flex gap-4">
             <Sparkles className="w-8 h-8 text-secondary flex-shrink-0" />
             <div>
               <p className="whitespace-pre-line leading-relaxed text-primary/90">{advice.data.advice}</p>
               {advice.data.generatedAt && (
                 <p className="text-xs text-muted-foreground mt-6 text-left" dir="ltr">
                   Generated: {new Date(advice.data.generatedAt).toLocaleString()}
                 </p>
               )}
             </div>
           </div>
         </div>
       )}
    </DialogWrapper>
  );
}

function RestructureDialog({ onClose }: { onClose: () => void }) {
  const plan = useGetRestructurePlan();
  
  useState(() => {
    plan.mutate();
  });

  return (
    <DialogWrapper title="خطة إعادة الهيكلة المقترحة" isOpen={true} onClose={onClose}>
      {plan.isPending ? <Loader2 className="w-8 h-8 animate-spin mx-auto text-secondary" /> : 
       plan.isError ? <p className="text-destructive">حدث خطأ</p> : 
       plan.data?.awaitingVerification ? <AwaitingVerificationNotice message={plan.data.message} /> :
       plan.data && (
         <div className="space-y-6">
           <div className="flex items-center justify-between p-4 bg-secondary/10 rounded-lg border border-secondary/20">
             <div className="text-center">
               <p className="text-sm text-muted-foreground">العبء الحالي</p>
               <p className="text-xl font-bold line-through text-muted-foreground">{plan.data.currentMonthlyBurden} د.أ</p>
             </div>
             <ArrowRightLeft className="w-6 h-6 text-secondary" />
             <div className="text-center">
               <p className="text-sm text-secondary font-bold">العبء المستهدف</p>
               <p className="text-2xl font-bold text-primary">{plan.data.targetMonthlyBurden} د.أ</p>
             </div>
           </div>

           <p className="text-center font-medium">المدة المتوقعة لتنفيذ الخطة: <span className="text-secondary">{plan.data.months} أشهر</span></p>

           <div className="relative border-r-2 border-primary/20 pr-6 mt-6 space-y-8">
             {(plan.data.steps ?? []).map((step, i) => (
               <div key={i} className="relative">
                 <div className="absolute -right-[35px] w-6 h-6 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-xs font-bold ring-4 ring-background">{i + 1}</div>
                 <h4 className="font-bold text-primary">{step.lenderName} — <span className="text-secondary">{step.action}</span></h4>
                 <p className="text-sm text-muted-foreground mt-1">{step.detail}</p>
               </div>
             ))}
           </div>
         </div>
       )}
    </DialogWrapper>
  );
}

function ConsolidationDialog({ onClose }: { onClose: () => void }) {
  const req = useRequestConsolidation();
  
  useState(() => {
    req.mutate();
  });

  return (
    <DialogWrapper title="طلب توحيد القروض" isOpen={true} onClose={onClose}>
      {req.isPending ? <Loader2 className="w-8 h-8 animate-spin mx-auto text-secondary" /> : 
       req.isError ? <p className="text-destructive">حدث خطأ</p> : 
       req.data?.awaitingVerification ? <AwaitingVerificationNotice message={req.data.message} /> :
       req.data && (
         <div className="text-center py-6 space-y-6">
           <div className="w-16 h-16 bg-green-100 text-green-600 rounded-full flex items-center justify-center mx-auto">
             <CheckCircle2 className="w-8 h-8" />
           </div>
           
           <div>
             <h3 className="text-xl font-bold mb-2">تم تسجيل طلبك المبدئي</h3>
             <p className="text-muted-foreground">رقم الطلب: #{req.data.id}</p>
           </div>
           
           <div className="bg-muted/30 p-6 rounded-xl inline-block text-right border">
             <p className="mb-2"><strong>المؤسسات المشمولة:</strong> {req.data.institutionsIncluded}</p>
             <p><strong>القسط الموحد التقديري:</strong> {(req.data.estimatedConsolidatedMonthlyPayment ?? 0).toLocaleString()} د.أ / شهر</p>
           </div>
           
           <p className="text-sm text-muted-foreground">سيقوم أحد مستشارينا بالتواصل معك قريباً لاستكمال الإجراءات.</p>
         </div>
       )}
    </DialogWrapper>
  );
}

function EligibilityDialog({ onClose }: { onClose: () => void }) {
  const check = useAssessLoanEligibility();
  
  useState(() => {
    check.mutate();
  });

  return (
    <DialogWrapper title="تقييم أهلية التمويل الإضافي" isOpen={true} onClose={onClose}>
      {check.isPending ? <Loader2 className="w-8 h-8 animate-spin mx-auto text-secondary" /> : 
       check.isError ? <p className="text-destructive">حدث خطأ</p> : 
       check.data && (
         <div className="space-y-6">
           {/* Credit Score */}
           <div className="p-6 rounded-xl border text-center bg-primary/5 border-primary/10">
             <p className="text-sm text-muted-foreground mb-2">درجتك الائتمانية</p>
             <p className="text-4xl font-extrabold" style={{ color: check.data.creditScoreColor }}>{check.data.creditScore}</p>
             <p className="text-sm font-medium mt-1" style={{ color: check.data.creditScoreColor }}>{check.data.creditScoreLabel}</p>
             <div className="w-full h-2 rounded-full bg-muted mt-4 overflow-hidden">
               <div
                 className="h-full rounded-full transition-all"
                 style={{ width: `${((check.data.creditScore - 300) / (850 - 300)) * 100}%`, backgroundColor: check.data.creditScoreColor }}
               />
             </div>
           </div>

           <div className={`p-6 rounded-xl border text-center ${check.data.eligible ? 'bg-green-50 border-green-200 text-green-800' : 'bg-destructive/5 border-destructive/20 text-destructive'}`}>
             <h3 className="text-2xl font-bold mb-2">
               {check.data.eligible ? "أنت مؤهل للحصول على تمويل إضافي" : "غير مؤهل حالياً لتمويل إضافي"}
             </h3>
             <p className="opacity-90">{check.data.recommendation}</p>
           </div>

           {check.data.eligible && (
             <div className="grid grid-cols-2 gap-4">
               <div className="p-4 bg-muted/30 rounded-lg text-center border">
                 <p className="text-sm text-muted-foreground">المبلغ الموصى به</p>
                 <p className="text-2xl font-bold text-primary">{check.data.recommendedAmount?.toLocaleString()} د.أ</p>
               </div>
               <div className="p-4 bg-muted/30 rounded-lg text-center border">
                 <p className="text-sm text-muted-foreground">القسط الشهري المتوقع</p>
                 <p className="text-2xl font-bold text-secondary">{check.data.monthlyInstallment?.toLocaleString()} د.أ</p>
               </div>
             </div>
           )}
         </div>
       )}
    </DialogWrapper>
  );
}
