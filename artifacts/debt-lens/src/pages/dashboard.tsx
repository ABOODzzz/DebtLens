import { useGetFinancialSummary, useAnalyzeFinances, useGetRestructurePlan, useGetAdvice, useRequestConsolidation, useAssessLoanEligibility, useGetGuarantorNetwork, useRequestGuarantor, useRespondToGuarantorRequest, getGetGuarantorNetworkQueryKey, GuarantorNetwork, GuarantorRelationshipSummary, useSubmitLoanApplication, useGetCurrentLoanApplication, getGetCurrentLoanApplicationQueryKey, LoanApplication } from "@workspace/api-client-react";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/lib/auth-context";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { AlertCircle, LineChart, PieChart, Sparkles, Building, ArrowRightLeft, Loader2, CheckCircle2, ShieldAlert, ShieldCheck, Users, BadgeCheck, Check, X, Wallet } from "lucide-react";
import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";

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
  const guarantorQuery = useGetGuarantorNetwork();
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
            <div className="flex items-center gap-3 mb-2 flex-wrap">
              <h1 className="text-3xl font-bold">أهلاً بك، {profile?.fullName?.split(' ')[0] || 'عميلنا العزيز'}</h1>
              {profile?.reviewStatus === 'approved' && (
                <span className="inline-flex items-center gap-1 bg-secondary/20 text-secondary text-sm font-medium px-3 py-1 rounded-full">
                  <BadgeCheck className="w-4 h-4" /> حساب موثّق
                </span>
              )}
            </div>
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

        <LoanApplicationCard guarantorNetwork={guarantorQuery.data} />

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

// --- Loan Application Card & Wizard ---
function loanApplicationStatusLabel(status: string) {
  switch (status) {
    case 'submitted': return 'تم الإرسال، قيد المراجعة النهائية';
    case 'awaiting_guarantor': return 'بانتظار كفيل رقمي';
    case 'rejected': return 'غير مؤهل حالياً';
    default: return status;
  }
}

function loanApplicationStatusClass(status: string) {
  switch (status) {
    case 'submitted': return 'bg-green-100 text-green-700';
    case 'awaiting_guarantor': return 'bg-yellow-100 text-yellow-700';
    case 'rejected': return 'bg-red-100 text-red-700';
    default: return 'bg-muted text-muted-foreground';
  }
}

function LoanApplicationCard({ guarantorNetwork }: { guarantorNetwork?: GuarantorNetwork }) {
  const applicationQuery = useGetCurrentLoanApplication();
  const [wizardOpen, setWizardOpen] = useState(false);

  const hasApplication = !applicationQuery.isError && !!applicationQuery.data;
  const application = applicationQuery.data;

  if (applicationQuery.isLoading) {
    return (
      <Card className="border-secondary/30">
        <CardContent className="p-6 flex items-center justify-center">
          <Loader2 className="w-6 h-6 animate-spin text-secondary" />
        </CardContent>
      </Card>
    );
  }

  if (!hasApplication) {
    return (
      <>
        <Card className="border-secondary bg-secondary/5 overflow-hidden">
          <CardContent className="p-6 flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="w-14 h-14 rounded-2xl bg-secondary/20 flex items-center justify-center text-secondary shrink-0">
                <Wallet className="w-7 h-7" />
              </div>
              <div>
                <h3 className="font-bold text-xl text-primary mb-1">جاهز لتمويل جديد؟</h3>
                <p className="text-sm text-muted-foreground">قدّم طلبك الآن وسنقيّم أهليتك فوراً، وإذا احتجت كفيلاً رقمياً نساعدك تطلبه من نفس المكان.</p>
              </div>
            </div>
            <Button size="lg" onClick={() => setWizardOpen(true)} className="shrink-0">
              طلب تمويل جديد
            </Button>
          </CardContent>
        </Card>
        {wizardOpen && <LoanApplicationDialog onClose={() => setWizardOpen(false)} />}
      </>
    );
  }

  return (
    <>
      <Card className="border-primary/20">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-lg flex items-center gap-2">
            <Wallet className="w-5 h-5 text-secondary" /> طلب التمويل الأخير
          </CardTitle>
          <span className={`px-3 py-1 rounded-full text-xs font-medium ${loanApplicationStatusClass(application!.status)}`}>
            {loanApplicationStatusLabel(application!.status)}
          </span>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-muted-foreground">المبلغ المطلوب</p>
              <p className="font-bold">{application!.requested_amount.toLocaleString()} د.أ</p>
            </div>
            <div>
              <p className="text-muted-foreground">الغرض</p>
              <p className="font-bold truncate">{application!.purpose}</p>
            </div>
          </div>

          {application!.status === 'submitted' && application!.recommended_amount != null && (
            <div className="grid grid-cols-2 gap-4 text-sm p-4 bg-green-50 border border-green-200 rounded-lg text-green-800">
              <div>
                <p className="opacity-80">المبلغ الموصى به</p>
                <p className="font-bold">{application!.recommended_amount.toLocaleString()} د.أ</p>
              </div>
              <div>
                <p className="opacity-80">القسط الشهري</p>
                <p className="font-bold">{application!.monthly_installment?.toLocaleString()} د.أ</p>
              </div>
            </div>
          )}

          <p className="text-sm text-muted-foreground leading-relaxed">{application!.recommendation}</p>

          {application!.status === 'awaiting_guarantor' && (
            <InlineGuarantorRequest application={application!} guarantorNetwork={guarantorNetwork} />
          )}

          {application!.status === 'rejected' && (
            <Button variant="outline" onClick={() => setWizardOpen(true)}>تقديم طلب جديد</Button>
          )}
        </CardContent>
      </Card>
      {wizardOpen && <LoanApplicationDialog onClose={() => setWizardOpen(false)} />}
    </>
  );
}

function InlineGuarantorRequest({ application, guarantorNetwork }: { application: LoanApplication; guarantorNetwork?: GuarantorNetwork }) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const requestMutation = useRequestGuarantor();
  const [nationalId, setNationalId] = useState("");

  const linkedRelationship = application.guarantor_relationship_id
    ? guarantorNetwork?.outgoing.find((r) => r.id === application.guarantor_relationship_id)
    : undefined;

  if (linkedRelationship) {
    return (
      <div className="flex items-center justify-between p-4 bg-blue-50 border border-blue-200 rounded-lg text-sm">
        <p className="text-blue-800">
          طلب كفالة من <strong>{linkedRelationship.guarantor_name}</strong> — {guarantorStatusLabel(linkedRelationship.status)}
        </p>
        <span className={`px-2 py-1 rounded-full text-xs font-medium shrink-0 ${guarantorStatusClass(linkedRelationship.status)}`}>
          {guarantorStatusLabel(linkedRelationship.status)}
        </span>
      </div>
    );
  }

  const handleRequest = async () => {
    if (!nationalId.trim()) return;
    try {
      const res = await requestMutation.mutateAsync({ data: { guarantor_national_id: nationalId.trim(), application_id: application.id } });
      toast({ title: "تم إرسال الطلب", description: `تم إرسال طلب الكفالة إلى ${res.guarantor_name}.` });
      setNationalId("");
      queryClient.invalidateQueries({ queryKey: getGetGuarantorNetworkQueryKey() });
      queryClient.invalidateQueries({ queryKey: getGetCurrentLoanApplicationQueryKey() });
    } catch (error: any) {
      toast({
        variant: "destructive",
        title: "تعذر إرسال الطلب",
        description: error?.error || "لم نتمكن من العثور على هذا الشخص أو أنه غير مؤهل ليكون كفيلاً رقمياً.",
      });
    }
  };

  return (
    <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg space-y-3">
      <p className="text-sm text-yellow-800">
        طلبك يحتاج كفيلاً رقمياً لإتمام الموافقة. أدخل الرقم الوطني لشخص موثّق عندنا ليكون كفيلك.
      </p>
      <div className="flex gap-2">
        <Input
          dir="ltr"
          placeholder="الرقم الوطني للكفيل"
          value={nationalId}
          onChange={(e) => setNationalId(e.target.value)}
        />
        <Button onClick={handleRequest} disabled={requestMutation.isPending || !nationalId.trim()}>
          {requestMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : "طلب كفيل"}
        </Button>
      </div>
    </div>
  );
}

function LoanApplicationDialog({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const submitMutation = useSubmitLoanApplication();
  const [requestedAmount, setRequestedAmount] = useState("");
  const [purpose, setPurpose] = useState("");

  const handleSubmit = () => {
    const amount = parseFloat(requestedAmount);
    if (!amount || amount <= 0 || !purpose.trim()) return;
    submitMutation.mutate(
      { data: { requested_amount: amount, purpose: purpose.trim() } },
      {
        onSuccess: () => {
          queryClient.invalidateQueries({ queryKey: getGetCurrentLoanApplicationQueryKey() });
        },
      },
    );
  };

  const result = submitMutation.data;

  return (
    <DialogWrapper title="طلب تمويل جديد" isOpen={true} onClose={onClose}>
      {!result && (
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="amount">المبلغ المطلوب (د.أ)</Label>
            <Input
              id="amount"
              type="number"
              min="1"
              dir="ltr"
              value={requestedAmount}
              onChange={(e) => setRequestedAmount(e.target.value)}
              placeholder="مثال: 1000"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="purpose">الغرض من التمويل</Label>
            <Textarea
              id="purpose"
              value={purpose}
              onChange={(e) => setPurpose(e.target.value)}
              placeholder="مثال: تجديد المنزل، شراء سيارة، توسيع مشروعي الخاص..."
              rows={3}
            />
          </div>
          {submitMutation.isError && (
            <p className="text-destructive text-sm">حدث خطأ أثناء إرسال الطلب، الرجاء المحاولة مرة أخرى.</p>
          )}
          <Button
            className="w-full"
            size="lg"
            onClick={handleSubmit}
            disabled={submitMutation.isPending || !requestedAmount || !purpose.trim()}
          >
            {submitMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : "إرسال الطلب"}
          </Button>
        </div>
      )}

      {result && (
        <div className="space-y-4">
          <div className={`p-6 rounded-xl border text-center ${result.status === 'submitted' ? 'bg-green-50 border-green-200 text-green-800' : result.status === 'awaiting_guarantor' ? 'bg-yellow-50 border-yellow-200 text-yellow-800' : 'bg-destructive/5 border-destructive/20 text-destructive'}`}>
            <h3 className="text-xl font-bold mb-2">{loanApplicationStatusLabel(result.status)}</h3>
            <p className="opacity-90 text-sm leading-relaxed">{result.recommendation}</p>
          </div>

          {result.status === 'submitted' && result.recommended_amount != null && (
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div className="p-4 bg-muted/30 rounded-lg text-center border">
                <p className="text-muted-foreground">المبلغ الموصى به</p>
                <p className="text-xl font-bold text-primary">{result.recommended_amount.toLocaleString()} د.أ</p>
              </div>
              <div className="p-4 bg-muted/30 rounded-lg text-center border">
                <p className="text-muted-foreground">القسط الشهري</p>
                <p className="text-xl font-bold text-secondary">{result.monthly_installment?.toLocaleString()} د.أ</p>
              </div>
            </div>
          )}

          {result.status === 'awaiting_guarantor' && (
            <p className="text-sm text-muted-foreground text-center">
              أغلق هذه النافذة وستجد في بطاقة "طلب التمويل الأخير" خياراً لطلب كفيل رقمي يدعم طلبك.
            </p>
          )}

          <Button className="w-full" variant="outline" onClick={onClose}>إغلاق</Button>
        </div>
      )}
    </DialogWrapper>
  );
}

// --- Guarantor Status Card ---
function guarantorStatusLabel(status: string) {
  switch (status) {
    case 'approved': return 'تمت الموافقة';
    case 'awaiting_admin_review': return 'بانتظار موافقة الإدارة';
    case 'declined': return 'رفض الكفيل';
    case 'rejected': return 'رفضته الإدارة';
    default: return 'قيد الانتظار';
  }
}

function guarantorStatusClass(status: string) {
  switch (status) {
    case 'approved': return 'bg-green-100 text-green-700';
    case 'awaiting_admin_review': return 'bg-blue-100 text-blue-700';
    case 'declined':
    case 'rejected': return 'bg-red-100 text-red-700';
    default: return 'bg-yellow-100 text-yellow-700';
  }
}

function GuarantorStatusCard({ data, isLoading, isError }: { data?: GuarantorNetwork; isLoading: boolean; isError: boolean }) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const requestMutation = useRequestGuarantor();
  const respondMutation = useRespondToGuarantorRequest();
  const [nationalId, setNationalId] = useState("");
  const [respondingId, setRespondingId] = useState<string | null>(null);
  const [historyTab, setHistoryTab] = useState<"active" | "pending" | "closed">("active");

  const invalidateNetwork = () => queryClient.invalidateQueries({ queryKey: getGetGuarantorNetworkQueryKey() });

  const handleRequest = async () => {
    if (!nationalId.trim()) return;
    try {
      const res = await requestMutation.mutateAsync({ data: { guarantor_national_id: nationalId.trim() } });
      toast({ title: "تم إرسال الطلب", description: `تم إرسال طلب الكفالة إلى ${res.guarantor_name}.` });
      setNationalId("");
      invalidateNetwork();
    } catch (error: any) {
      toast({
        variant: "destructive",
        title: "تعذر إرسال الطلب",
        description: error?.error || "لم نتمكن من العثور على هذا الشخص أو أنه غير مؤهل ليكون كفيلاً رقمياً.",
      });
    }
  };

  const handleRespond = async (relationshipId: string, approve: boolean) => {
    setRespondingId(relationshipId);
    try {
      await respondMutation.mutateAsync({ data: { relationship_id: relationshipId, approve } });
      invalidateNetwork();
    } catch (error) {
      toast({ variant: "destructive", title: "تعذر تسجيل الرد", description: "يرجى المحاولة مرة أخرى." });
    } finally {
      setRespondingId(null);
    }
  };

  if (isLoading) return null;
  if (isError || !data) return null;

  const { outgoing, incoming, guarantor_capacity, requester_capacity } = data;
  const allRelationships = [...outgoing, ...incoming];
  const activeRelationships = allRelationships.filter((r) => r.status === "approved");
  const pendingIncoming = incoming.filter((r) => r.status === "pending");
  const pendingOutgoing = outgoing.filter((r) => r.status === "pending" || r.status === "awaiting_admin_review");
  const closedRelationships = allRelationships.filter((r) => r.status === "declined" || r.status === "rejected");
  const canRequestNewGuarantor = requester_capacity.used_count < requester_capacity.max_count;

  return (
    <Card className="border-secondary/20 bg-secondary/5">
      <CardContent className="p-6 space-y-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-secondary/20 flex items-center justify-center text-primary shrink-0">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <h3 className="font-bold text-primary">الكفيل الرقمي</h3>
            <p className="text-sm text-muted-foreground">اطلب من عميل موثّق أن يكفلك، أو راجع طلبات الكفالة الواردة إليك</p>
          </div>
        </div>

        {/* Capacity summary */}
        <div className="grid grid-cols-2 gap-3 text-xs">
          <div className="p-2.5 bg-background border rounded-lg">
            <p className="text-muted-foreground mb-0.5">كفلاؤك</p>
            <p className="font-bold text-primary">{requester_capacity.used_count} / {requester_capacity.max_count}</p>
          </div>
          <div className="p-2.5 bg-background border rounded-lg">
            <p className="text-muted-foreground mb-0.5">من تكفلهم أنت</p>
            <p className="font-bold text-primary">{guarantor_capacity.used_count} / {guarantor_capacity.max_count} (حتى {guarantor_capacity.max_amount.toLocaleString()} د.أ)</p>
          </div>
        </div>

        {pendingIncoming.length > 0 && (
          <div>
            <p className="text-sm font-medium mb-2 flex items-center gap-2">
              <Users className="w-4 h-4" /> طلبات كفالة واردة إليك
            </p>
            <div className="space-y-2">
              {pendingIncoming.map((request) => (
                <div key={request.id} className="flex items-center justify-between p-3 bg-muted/30 border rounded-lg text-sm gap-2">
                  <span className="truncate">{request.requester_name} (بحد أقصى {request.max_amount.toLocaleString()} د.أ)</span>
                  <div className="flex gap-2 shrink-0">
                    <Button
                      size="sm"
                      variant="outline"
                      className="bg-green-50 text-green-700 hover:bg-green-100 border-green-200"
                      disabled={respondMutation.isPending && respondingId === request.id}
                      onClick={() => handleRespond(request.id, true)}
                    >
                      {respondMutation.isPending && respondingId === request.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="bg-red-50 text-red-700 hover:bg-red-100 border-red-200"
                      disabled={respondMutation.isPending && respondingId === request.id}
                      onClick={() => handleRespond(request.id, false)}
                    >
                      {respondMutation.isPending && respondingId === request.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <X className="w-4 h-4" />}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {canRequestNewGuarantor && (
          <div className="p-3 bg-background border rounded-lg space-y-2">
            <Label htmlFor="guarantor-national-id" className="text-sm font-medium">طلب كفيل رقمي جديد</Label>
            <div className="flex gap-2">
              <Input
                id="guarantor-national-id"
                placeholder="الرقم الوطني للكفيل"
                value={nationalId}
                onChange={(e) => setNationalId(e.target.value)}
                dir="ltr"
                className="text-right"
              />
              <Button onClick={handleRequest} disabled={requestMutation.isPending || !nationalId.trim()} className="shrink-0">
                {requestMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : "إرسال الطلب"}
              </Button>
            </div>
          </div>
        )}

        {/* Guarantee history */}
        {allRelationships.length > 0 && (
          <div>
            <div className="flex gap-1 mb-2 border-b">
              {(
                [
                  { key: "active", label: `نشطة (${activeRelationships.length})` },
                  { key: "pending", label: `قيد الانتظار (${pendingOutgoing.length + pendingIncoming.length})` },
                  { key: "closed", label: `مرفوضة/منتهية (${closedRelationships.length})` },
                ] as const
              ).map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => setHistoryTab(tab.key)}
                  className={`px-3 py-1.5 text-xs font-medium border-b-2 transition-colors ${
                    historyTab === tab.key ? "border-secondary text-primary" : "border-transparent text-muted-foreground hover:text-primary"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            <div className="space-y-2">
              {(historyTab === "active"
                ? activeRelationships
                : historyTab === "pending"
                ? [...pendingOutgoing, ...pendingIncoming]
                : closedRelationships
              ).map((rel) => (
                <GuarantorHistoryRow key={rel.id} rel={rel} />
              ))}
              {(historyTab === "active"
                ? activeRelationships
                : historyTab === "pending"
                ? [...pendingOutgoing, ...pendingIncoming]
                : closedRelationships
              ).length === 0 && <p className="text-xs text-muted-foreground py-3 text-center">لا توجد سجلات في هذه الفئة</p>}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function GuarantorHistoryRow({ rel }: { rel: GuarantorRelationshipSummary }) {
  const { user } = useAuth();
  const isRequesterMe = rel.requester_uid === user?.uid;
  const otherName = isRequesterMe ? rel.guarantor_name : rel.requester_name;
  const roleLabel = isRequesterMe ? "كفيلك" : "تكفله أنت";
  return (
    <div className="flex items-center justify-between p-3 bg-muted/30 border rounded-lg text-sm gap-2">
      <div className="min-w-0">
        <p className="truncate">
          <span className="text-muted-foreground text-xs">{roleLabel}: </span>
          {otherName} <span className="text-muted-foreground text-xs">({rel.max_amount.toLocaleString()} د.أ)</span>
        </p>
      </div>
      <span className={`px-2 py-1 rounded-full text-xs font-medium shrink-0 ${guarantorStatusClass(rel.status)}`}>
        {guarantorStatusLabel(rel.status)}
      </span>
    </div>
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
