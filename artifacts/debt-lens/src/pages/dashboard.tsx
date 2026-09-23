import { useGetFinancialSummary, getGetFinancialSummaryQueryKey, useAnalyzeFinances, useGetRestructurePlan, useGetAdvice, useRequestConsolidation, useAssessLoanEligibility, useGetGuarantorNetwork, useRequestGuarantor, useRespondToGuarantorRequest, getGetGuarantorNetworkQueryKey, GuarantorNetwork, GuarantorRelationshipSummary, useSubmitLoanApplication, useGetCurrentLoanApplication, getGetCurrentLoanApplicationQueryKey, LoanApplication } from "@workspace/api-client-react";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/lib/auth-context";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { AlertCircle, LineChart, PieChart, Sparkles, Building, ArrowRightLeft, Loader2, CheckCircle2, ShieldAlert, ShieldCheck, Users, BadgeCheck, Check, X, Wallet } from "lucide-react";
import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";
import { useLanguage } from "@/lib/i18n/context";
import { auth } from "@/lib/firebase";
import { db } from "@/lib/firebase";
import { doc, updateDoc } from "firebase/firestore";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, PieChart as RechartsPieChart, Pie, Cell, Legend } from "recharts";

const CHART_COLORS = ["#17365D", "#EAB308", "#0F766E", "#DC2626", "#7C3AED", "#0284C7"];

export default function DashboardPage() {
  const { profile } = useAuth();
  const { t } = useLanguage();
  
  // Status check
  if (profile?.reviewStatus === "pending") {
    return (
      <div className="flex-1 container mx-auto p-4 md:p-8 max-w-3xl flex items-center justify-center">
        <Card className="glass-card text-center py-16 px-8 w-full border-secondary/20">
          <Loader2 className="w-16 h-16 animate-spin text-secondary mx-auto mb-6" />
          <h2 className="text-2xl font-bold text-primary mb-2">{t("dashboard.review.pending")}</h2>
          <p className="text-muted-foreground">{t("dashboard.review.pendingBody")}</p>
        </Card>
      </div>
    );
  }

  if (profile?.reviewStatus === "rejected") {
    return (
      <div className="flex-1 container mx-auto p-4 md:p-8 max-w-3xl flex items-center justify-center">
        <Card className="border-destructive/20 text-center py-16 px-8 w-full bg-destructive/5">
          <ShieldAlert className="w-16 h-16 text-destructive mx-auto mb-6" />
          <h2 className="text-2xl font-bold text-destructive mb-2">{t("dashboard.review.rejected")}</h2>
          <p className="text-muted-foreground mb-4">{t("dashboard.application.reason")}: {profile.reviewReason || t("dashboard.review.defaultReason")}</p>
          <Button variant="outline" onClick={() => window.location.href="/wizard"}>{t("dashboard.review.resubmit")}</Button>
        </Card>
      </div>
    );
  }

  // Dashboard for approved users
  return <DashboardContent />;
}

function DashboardContent() {
  const { profile } = useAuth();
  const { t, language } = useLanguage();
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
        <p>{t("dashboard.error.financial")}</p>
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
              <h1 className="text-3xl font-bold">{t("dashboard.welcome.greeting", { name: profile?.fullName?.split(' ')[0] || t("dashboard.welcome.customer") })}</h1>
              {profile?.reviewStatus === 'approved' && (
                <span className="inline-flex items-center gap-1 bg-secondary/20 text-secondary text-sm font-medium px-3 py-1 rounded-full">
                  <BadgeCheck className="w-4 h-4" /> {t("dashboard.welcome.verified")}
                </span>
              )}
            </div>
            <p className="text-primary-foreground/80">{t("dashboard.welcome.summary")}</p>
          </div>
          <div className="bg-primary-foreground/10 px-6 py-4 rounded-xl backdrop-blur-sm border border-primary-foreground/20 text-center min-w-[200px]">
            <p className="text-sm opacity-80 mb-1">{t("dashboard.welcome.debtTotal")}</p>
            <p className="text-3xl font-bold text-secondary">{summary.totalRemainingDebt.toLocaleString(language === "ar" ? "ar-JO" : "en-US")} <span className="text-lg">{t("common.currency")}</span></p>
          </div>
        </div>
      </div>

      <div className="container mx-auto max-w-6xl px-4 mt-8 space-y-8">

        {!isVerified && (
          <div className="flex items-start gap-3 bg-secondary/10 border border-secondary/30 rounded-lg p-4 text-sm">
            <AlertCircle className="w-5 h-5 text-secondary flex-shrink-0 mt-0.5" />
            <p className="text-muted-foreground">
              {t("dashboard.welcome.unverified")}
            </p>
          </div>
        )}
        {summary.totalMonthlyIncome <= 0 && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-400 bg-amber-50 p-4 text-sm text-primary">
            <span>{t("dashboard.obligations.missingIncome")}</span>
            <Button size="sm" onClick={() => setActiveDialog("full-analysis")}>
              {t("dashboard.obligations.completeDetails")}
            </Button>
          </div>
        )}

        {/* KPI Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiCard title={t("dashboard.kpi.income")} value={summary.totalMonthlyIncome} unit={t("common.currency")} />
          <KpiCard title={t("dashboard.kpi.payments")} value={summary.totalMonthlyDebtPayments} unit={t("common.currency")} highlight={summary.totalMonthlyDebtPayments > summary.totalMonthlyIncome * 0.5} />
          <KpiCard title={t("dashboard.kpi.ratio")} value={Math.round(summary.debtToIncomeRatio)} unit="%" highlight={summary.debtToIncomeRatio > 50} />
          <KpiCard title={t("dashboard.kpi.loans")} value={summary.activeLoansCount} unit="" isNumber />
        </div>

        <LoanApplicationCard guarantorNetwork={guarantorQuery.data} />

        <GuarantorStatusCard
          data={guarantorQuery.data}
          isLoading={guarantorQuery.isLoading}
          isError={guarantorQuery.isError}
        />

        <h2 className="text-xl font-bold text-primary border-b pb-2">{t("dashboard.services.heading")}</h2>
        
        {/* Services Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          
          <ServiceCard 
            title={t("dashboard.services.analysis.title")} 
            description={t("dashboard.services.analysis.description")}
            icon={<PieChart className="w-6 h-6" />}
            onClick={() => setActiveDialog('full-analysis')}
          />
          
          <ServiceCard 
            title={t("dashboard.services.advice.title")} 
            description={t("dashboard.services.advice.description")}
            icon={<Sparkles className="w-6 h-6 text-secondary" />}
            onClick={() => setActiveDialog('ai-advice')}
          />

          {summary.hasActiveLoans && (
            <ServiceCard 
              title={t("dashboard.services.restructure.title")} 
              description={t("dashboard.services.restructure.description")}
              icon={<ArrowRightLeft className="w-6 h-6" />}
              onClick={() => setActiveDialog('restructure')}
            />
          )}

          {summary.hasMultipleFinancingInstitutions && (
            <ServiceCard 
              title={t("dashboard.services.consolidation.title")} 
              description={t("dashboard.services.consolidation.description")}
              icon={<Building className="w-6 h-6" />}
              onClick={() => setActiveDialog('consolidation')}
            />
          )}
          
          <ServiceCard 
            title={t("dashboard.services.eligibility.title")} 
            description={t("dashboard.services.eligibility.description")}
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
function loanApplicationStatusLabel(status: string, t: (key: string) => string) {
  switch (status) {
    case 'submitted': return t("dashboard.status.submitted");
    case 'awaiting_guarantor': return t("dashboard.status.awaiting");
    case 'approved': return t("dashboard.status.approved");
    case 'admin_rejected': return t("dashboard.status.adminRejected");
    case 'rejected': return t("dashboard.status.rejected");
    default: return status;
  }
}

function loanApplicationStatusClass(status: string) {
  switch (status) {
    case 'submitted': return 'bg-green-100 text-green-700';
    case 'awaiting_guarantor': return 'bg-yellow-100 text-yellow-700';
    case 'approved': return 'bg-green-100 text-green-700';
    case 'admin_rejected': return 'bg-red-100 text-red-700';
    case 'rejected': return 'bg-red-100 text-red-700';
    default: return 'bg-muted text-muted-foreground';
  }
}

function LoanApplicationCard({ guarantorNetwork }: { guarantorNetwork?: GuarantorNetwork }) {
  const { t, language } = useLanguage();
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
                <h3 className="font-bold text-xl text-primary mb-1">{t("dashboard.application.ready")}</h3>
                <p className="text-sm text-muted-foreground">{t("dashboard.application.readyBody")}</p>
              </div>
            </div>
            <Button size="lg" onClick={() => setWizardOpen(true)} className="shrink-0">
              {t("dashboard.application.new")}
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
             <Wallet className="w-5 h-5 text-secondary" /> {t("dashboard.application.latest")}
          </CardTitle>
          <span className={`px-3 py-1 rounded-full text-xs font-medium ${loanApplicationStatusClass(application!.status)}`}>
            {loanApplicationStatusLabel(application!.status, t)}
          </span>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-muted-foreground">{t("dashboard.application.requested")}</p>
              <p className="font-bold">{application!.requested_amount.toLocaleString(language === "ar" ? "ar-JO" : "en-US")} {t("common.currency")}</p>
            </div>
            <div>
              <p className="text-muted-foreground">{t("dashboard.application.purpose")}</p>
              <p className="font-bold truncate">{application!.purpose}</p>
            </div>
          </div>

          {(application!.status === 'submitted' || application!.status === 'approved') && application!.recommended_amount != null && (
            <div className="grid grid-cols-2 gap-4 text-sm p-4 bg-green-50 border border-green-200 rounded-lg text-green-800">
              <div>
                <p className="opacity-80">{t("dashboard.application.recommended")}</p>
                <p className="font-bold">{application!.recommended_amount.toLocaleString(language === "ar" ? "ar-JO" : "en-US")} {t("common.currency")}</p>
              </div>
              <div>
                <p className="opacity-80">{t("dashboard.application.installment")}</p>
                <p className="font-bold">{application!.monthly_installment?.toLocaleString(language === "ar" ? "ar-JO" : "en-US")} {t("common.currency")}</p>
              </div>
            </div>
          )}

          <p className="text-sm text-muted-foreground leading-relaxed">{application!.recommendation}</p>

          {application!.status === 'awaiting_guarantor' && (
            <InlineGuarantorRequest application={application!} guarantorNetwork={guarantorNetwork} />
          )}

          {application!.status === 'admin_rejected' && application!.admin_decision_reason && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800">
              {t("dashboard.application.reason")}: {application!.admin_decision_reason}
            </div>
          )}

          {(application!.status === 'rejected' || application!.status === 'admin_rejected') && (
            <Button variant="outline" onClick={() => setWizardOpen(true)}>{t("dashboard.application.newRequest")}</Button>
          )}
        </CardContent>
      </Card>
      {wizardOpen && <LoanApplicationDialog onClose={() => setWizardOpen(false)} />}
    </>
  );
}

function InlineGuarantorRequest({ application, guarantorNetwork }: { application: LoanApplication; guarantorNetwork?: GuarantorNetwork }) {
  const { t } = useLanguage();
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
          {t("dashboard.guarantor.request")}: <strong>{linkedRelationship.guarantor_name}</strong> — {guarantorStatusLabel(linkedRelationship.status, t)}
        </p>
        <span className={`px-2 py-1 rounded-full text-xs font-medium shrink-0 ${guarantorStatusClass(linkedRelationship.status)}`}>
          {guarantorStatusLabel(linkedRelationship.status, t)}
        </span>
      </div>
    );
  }

  const handleRequest = async () => {
    if (!nationalId.trim()) return;
    try {
      const res = await requestMutation.mutateAsync({ data: { guarantor_national_id: nationalId.trim(), application_id: application.id } });
      toast({ title: t("dashboard.guarantor.requestSent"), description: t("dashboard.guarantor.requestSentTo", { name: res.guarantor_name }) });
      setNationalId("");
      queryClient.invalidateQueries({ queryKey: getGetGuarantorNetworkQueryKey() });
      queryClient.invalidateQueries({ queryKey: getGetCurrentLoanApplicationQueryKey() });
    } catch (error: any) {
      toast({
        variant: "destructive",
        title: t("dashboard.guarantor.requestFailed"),
        description: error?.error || t("dashboard.error.guarantor"),
      });
    }
  };

  return (
    <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg space-y-3">
      <p className="text-sm text-yellow-800">
          {t("dashboard.guarantor.applicationNeed")}
      </p>
      <div className="flex gap-2">
        <Input
          dir="ltr"
          placeholder={t("dashboard.guarantor.nationalId")}
          value={nationalId}
          onChange={(e) => setNationalId(e.target.value)}
        />
        <Button onClick={handleRequest} disabled={requestMutation.isPending || !nationalId.trim()}>
          {requestMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : t("dashboard.guarantor.request")}
        </Button>
      </div>
    </div>
  );
}

function LoanApplicationDialog({ onClose }: { onClose: () => void }) {
  const { t, language } = useLanguage();
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
    <DialogWrapper title={t("dashboard.application.new")} isOpen={true} onClose={onClose}>
      {!result && (
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="amount">{t("dashboard.application.amountLabel", { currency: t("common.currency") })}</Label>
            <Input
              id="amount"
              type="number"
              min="1"
              dir="ltr"
              value={requestedAmount}
              onChange={(e) => setRequestedAmount(e.target.value)}
              placeholder={t("dashboard.application.amountPlaceholder")}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="purpose">{t("dashboard.application.purposeLabel")}</Label>
            <Textarea
              id="purpose"
              value={purpose}
              onChange={(e) => setPurpose(e.target.value)}
              placeholder={t("dashboard.application.purposePlaceholder")}
              rows={3}
            />
          </div>
          {submitMutation.isError && (
            <p className="text-destructive text-sm">{t("dashboard.error.submit")}</p>
          )}
          <Button
            className="w-full"
            size="lg"
            onClick={handleSubmit}
            disabled={submitMutation.isPending || !requestedAmount || !purpose.trim()}
          >
            {submitMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : t("dashboard.application.send")}
          </Button>
        </div>
      )}

      {result && (
        <div className="space-y-4">
          <div className={`p-6 rounded-xl border text-center ${result.status === 'submitted' ? 'bg-green-50 border-green-200 text-green-800' : result.status === 'awaiting_guarantor' ? 'bg-yellow-50 border-yellow-200 text-yellow-800' : 'bg-destructive/5 border-destructive/20 text-destructive'}`}>
            <h3 className="text-xl font-bold mb-2">{loanApplicationStatusLabel(result.status, t)}</h3>
            <p className="opacity-90 text-sm leading-relaxed">{result.recommendation}</p>
          </div>

          {result.status === 'submitted' && result.recommended_amount != null && (
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div className="p-4 bg-muted/30 rounded-lg text-center border">
                <p className="text-muted-foreground">{t("dashboard.application.recommended")}</p>
                <p className="text-xl font-bold text-primary">{result.recommended_amount.toLocaleString(language === "ar" ? "ar-JO" : "en-US")} {t("common.currency")}</p>
              </div>
              <div className="p-4 bg-muted/30 rounded-lg text-center border">
                <p className="text-muted-foreground">{t("dashboard.application.installment")}</p>
                <p className="text-xl font-bold text-secondary">{result.monthly_installment?.toLocaleString(language === "ar" ? "ar-JO" : "en-US")} {t("common.currency")}</p>
              </div>
            </div>
          )}

          {result.status === 'awaiting_guarantor' && (
            <p className="text-sm text-muted-foreground text-center">
              {t("dashboard.application.guarantorNote")}
            </p>
          )}

          <Button className="w-full" variant="outline" onClick={onClose}>{t("dashboard.application.close")}</Button>
        </div>
      )}
    </DialogWrapper>
  );
}

// --- Guarantor Status Card ---
function guarantorStatusLabel(status: string, t: (key: string) => string) {
  switch (status) {
    case 'approved': return t("dashboard.status.approved");
    case 'awaiting_admin_review': return t("dashboard.status.awaiting");
    case 'declined': return t("dashboard.status.rejected");
    case 'rejected': return t("dashboard.status.adminRejected");
    default: return t("dashboard.status.awaiting");
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
  const { t, language } = useLanguage();
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
      toast({ title: t("dashboard.guarantor.requestSent"), description: t("dashboard.guarantor.requestSentTo", { name: res.guarantor_name }) });
      setNationalId("");
      invalidateNetwork();
    } catch (error: any) {
      toast({
        variant: "destructive",
        title: t("dashboard.guarantor.requestFailed"),
        description: error?.error || t("dashboard.error.guarantor"),
      });
    }
  };

  const handleRespond = async (relationshipId: string, approve: boolean) => {
    setRespondingId(relationshipId);
    try {
      await respondMutation.mutateAsync({ data: { relationship_id: relationshipId, approve } });
      invalidateNetwork();
    } catch (error) {
      toast({ variant: "destructive", title: t("dashboard.guarantor.responseFailed"), description: t("dashboard.error.retry") });
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
            <h3 className="font-bold text-primary">{t("dashboard.guarantor.digital")}</h3>
            <p className="text-sm text-muted-foreground">{t("dashboard.guarantor.intro")}</p>
          </div>
        </div>

        {/* Capacity summary */}
        <div className="grid grid-cols-2 gap-3 text-xs">
          <div className="p-2.5 bg-background border rounded-lg">
            <p className="text-muted-foreground mb-0.5">{t("dashboard.guarantor.yourGuarantors")}</p>
            <p className="font-bold text-primary">{requester_capacity.used_count} / {requester_capacity.max_count}</p>
          </div>
          <div className="p-2.5 bg-background border rounded-lg">
            <p className="text-muted-foreground mb-0.5">{t("dashboard.guarantor.guaranteed")}</p>
            <p className="font-bold text-primary">{guarantor_capacity.used_count} / {guarantor_capacity.max_count} ({t("dashboard.guarantor.max", { amount: guarantor_capacity.max_amount.toLocaleString(language === "ar" ? "ar-JO" : "en-US"), currency: t("common.currency") })})</p>
          </div>
        </div>

        {pendingIncoming.length > 0 && (
          <div>
              <p className="text-sm font-medium mb-2 flex items-center gap-2">
               <Users className="w-4 h-4" /> {t("dashboard.guarantor.incoming")}
            </p>
            <div className="space-y-2">
              {pendingIncoming.map((request) => (
                <div key={request.id} className="flex items-center justify-between p-3 bg-muted/30 border rounded-lg text-sm gap-2">
                  <span className="truncate">{request.requester_name} ({t("dashboard.guarantor.maxAmount", { amount: request.max_amount.toLocaleString(language === "ar" ? "ar-JO" : "en-US"), currency: t("common.currency") })})</span>
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
            <Label htmlFor="guarantor-national-id" className="text-sm font-medium">{t("dashboard.guarantor.newRequest")}</Label>
            <div className="flex gap-2">
              <Input
                id="guarantor-national-id"
                placeholder={t("dashboard.guarantor.nationalId")}
                value={nationalId}
                onChange={(e) => setNationalId(e.target.value)}
                dir="ltr"
                className="text-right"
              />
              <Button onClick={handleRequest} disabled={requestMutation.isPending || !nationalId.trim()} className="shrink-0">
                {requestMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : t("dashboard.application.send")}
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
                   { key: "active", label: t("dashboard.guarantor.active", { count: activeRelationships.length }) },
                   { key: "pending", label: t("dashboard.guarantor.pending", { count: pendingOutgoing.length + pendingIncoming.length }) },
                   { key: "closed", label: t("dashboard.guarantor.closed", { count: closedRelationships.length }) },
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
               ).length === 0 && <p className="text-xs text-muted-foreground py-3 text-center">{t("dashboard.guarantor.empty")}</p>}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function GuarantorHistoryRow({ rel }: { rel: GuarantorRelationshipSummary }) {
  const { user } = useAuth();
  const { t, language, dir } = useLanguage();
  const isRequesterMe = rel.requester_uid === user?.uid;
  const otherName = isRequesterMe ? rel.guarantor_name : rel.requester_name;
  const roleLabel = isRequesterMe ? t("dashboard.guarantor.yourGuarantor") : t("dashboard.guarantor.youGuarantee");
  return (
    <div className="flex items-center justify-between p-3 bg-muted/30 border rounded-lg text-sm gap-2">
      <div className="min-w-0">
        <p className="truncate">
          <span className="text-muted-foreground text-xs">{roleLabel}: </span>
          {otherName} <span className="text-muted-foreground text-xs">({rel.max_amount.toLocaleString(language === "ar" ? "ar-JO" : "en-US")} {t("common.currency")})</span>
        </p>
      </div>
      <span className={`px-2 py-1 rounded-full text-xs font-medium shrink-0 ${guarantorStatusClass(rel.status)}`}>
        {guarantorStatusLabel(rel.status, t)}
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
  const { t } = useLanguage();
  return (
    <div className="flex flex-col items-center text-center gap-3 py-6">
      <AlertCircle className="w-10 h-10 text-secondary" />
      <p className="text-muted-foreground leading-relaxed">
        {message || t("dashboard.dialogs.awaiting")}
      </p>
    </div>
  );
}

const DialogWrapper = ({ title, isOpen, onClose, children }: { title: string, isOpen: boolean, onClose: () => void, children: React.ReactNode }) => {
  const { dir } = useLanguage();
  return (
  <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
    <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto" dir={dir}>
      <DialogHeader>
        <DialogTitle className="text-xl text-primary">{title}</DialogTitle>
      </DialogHeader>
      <div className="py-4">
        {children}
      </div>
    </DialogContent>
  </Dialog>
  );
};

function FinancialDetailsForm({ needIncome, needObligations, onSaved }: {
  needIncome: boolean;
  needObligations: boolean;
  onSaved: () => void;
}) {
  const { profile } = useAuth();
  const { t } = useLanguage();
  const queryClient = useQueryClient();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [income, setIncome] = useState(String(profile?.monthlyIncome || ""));
  const [obligations, setObligations] = useState([
    { category: "rent", label: t("dashboard.obligations.rent"), amount: "" },
    { category: "utilities", label: t("dashboard.obligations.utilities"), amount: "" },
    { category: "transport", label: t("dashboard.obligations.transport"), amount: "" },
    { category: "loans", label: t("dashboard.obligations.loans"), amount: "" },
    { category: "family", label: t("dashboard.obligations.family"), amount: "" },
    { category: "other", label: t("dashboard.obligations.other"), amount: "" },
  ]);

  const saveDetails = async () => {
    const parsedIncome = Number(income);
    if (needIncome && (!Number.isFinite(parsedIncome) || parsedIncome <= 0)) {
      setError(t("dashboard.obligations.invalidIncome"));
      return;
    }
    const clean = obligations
      .map((item) => ({ ...item, amount: Number(item.amount || 0) }))
      .filter((item) => item.amount > 0);
    if (needObligations && obligations.some((item) => item.amount !== "" && (!Number.isFinite(Number(item.amount)) || Number(item.amount) < 0))) {
      setError(t("dashboard.obligations.invalidAmount"));
      return;
    }
    setError("");
    setSaving(true);
    try {
      if (needIncome) {
        if (!auth.currentUser) throw new Error("Not signed in");
        await updateDoc(doc(db, "users", auth.currentUser.uid), {
          monthlyIncome: parsedIncome,
          updatedAt: new Date().toISOString(),
        });
      }
      if (needObligations) {
      const token = await auth.currentUser?.getIdToken();
      const response = await fetch("/api/manual-obligations", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ obligations: clean }),
      });
      if (!response.ok) throw new Error("Unable to save obligations");
      }
      await queryClient.invalidateQueries({ queryKey: getGetFinancialSummaryQueryKey() });
      onSaved();
    } catch {
      setError(t("dashboard.obligations.saveError"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-secondary/30 bg-secondary/5 p-4">
        <h3 className="font-bold text-primary">{t("dashboard.obligations.title")}</h3>
        <p className="text-sm text-muted-foreground mt-1">{t("dashboard.obligations.description")}</p>
      </div>
      {needIncome && (
        <div>
          <Label htmlFor="financial-income">{t("dashboard.obligations.income")}</Label>
          <Input id="financial-income" type="number" min="0" step="0.01" value={income}
            onChange={(event) => setIncome(event.target.value)} className="mt-1" />
        </div>
      )}
      {needObligations && (
        <div className="grid sm:grid-cols-2 gap-4">
          {obligations.map((item, index) => (
            <div key={item.category}>
              <Label htmlFor={`obligation-${item.category}`}>{item.label}</Label>
              <Input id={`obligation-${item.category}`} type="number" min="0" step="0.01"
                value={item.amount}
                onChange={(event) => setObligations((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, amount: event.target.value } : row))}
                placeholder="0" className="mt-1" />
            </div>
          ))}
        </div>
      )}
      {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
      <Button className="w-full" disabled={saving} onClick={saveDetails}>
        {saving ? <Loader2 className="w-4 h-4 animate-spin me-2" /> : <Sparkles className="w-4 h-4 me-2" />}
        {t("dashboard.obligations.analyze")}
      </Button>
    </div>
  );
}

function FullAnalysisDialog({ onClose }: { onClose: () => void }) {
  const { profile } = useAuth();
  const { t, language } = useLanguage();
  const summaryQuery = useGetFinancialSummary();
  const analysis = useAnalyzeFinances();
  const needIncome = (summaryQuery.data?.totalMonthlyIncome ?? 0) <= 0;
  const needObligations = summaryQuery.data?.dataSource !== "verified" && !profile?.manualObligationsDeclared;
  const [collectingObligations, setCollectingObligations] = useState(needIncome || needObligations);

  useEffect(() => {
    if (!collectingObligations) analysis.mutate({ data: { type: "full" } });
  }, []);

  const data = analysis.data as any;

  return (
    <DialogWrapper title={t("dashboard.dialogs.analysis")} isOpen={true} onClose={onClose}>
      {collectingObligations ? (
        <FinancialDetailsForm needIncome={needIncome} needObligations={needObligations}
          onSaved={() => { setCollectingObligations(false); analysis.mutate({ data: { type: "full" } }); }} />
      ) : analysis.isPending ? <Loader2 className="w-8 h-8 animate-spin mx-auto text-secondary" /> : 
       analysis.isError ? <p className="text-destructive">{t("dashboard.error.generic")}</p> : 
       data?.awaitingVerification ? <AwaitingVerificationNotice message={data.message} /> :
       data && (
         <div className="space-y-6">
           <p className="text-lg leading-relaxed text-primary">{data.summary}</p>
           {data.bankAnalysis && (
             <p className="text-sm rounded-lg border border-secondary/30 bg-secondary/5 p-3">
               {t("dashboard.bankAnalysis.verifiedData")}
               {data.incomeSource !== "bank_salary" && ` ${t("dashboard.bankAnalysis.declaredIncome")}`}
             </p>
           )}
           
           <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
             <div className="p-4 bg-muted/30 rounded-lg">
                <p className="text-sm text-muted-foreground">{t("dashboard.dialogs.debtTotal")}</p>
                 <p className="text-xl font-bold">{(data.totalRemainingDebt ?? 0).toLocaleString(language === "ar" ? "ar-JO" : "en-US")} {t("common.currency")}</p>
             </div>
             <div className="p-4 bg-muted/30 rounded-lg">
                <p className="text-sm text-muted-foreground">{t("dashboard.dialogs.burden")}</p>
                <p className="text-xl font-bold text-secondary">{Math.round(data.debtToIncomeRatio ?? 0)}%</p>
             </div>
             <div className="p-4 bg-muted/30 rounded-lg">
                <p className="text-sm text-muted-foreground">{t("dashboard.obligations.total")}</p>
                <p className="text-xl font-bold">{(data.monthlyObligations ?? 0).toLocaleString(language === "ar" ? "ar-JO" : "en-US")} {t("common.currency")}</p>
             </div>
             <div className="p-4 bg-muted/30 rounded-lg">
                <p className="text-sm text-muted-foreground">{t("dashboard.obligations.disposable")}</p>
                <p className="text-xl font-bold text-green-700">{(data.disposableIncome ?? 0).toLocaleString(language === "ar" ? "ar-JO" : "en-US")} {t("common.currency")}</p>
             </div>
           </div>

           {data.bankAnalysis && (
             <>
               <h4 className="font-bold text-primary">{t("dashboard.bankAnalysis.title")}</h4>
               <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                 {([
                   ["credits", data.bankAnalysis.summary.total_credits],
                   ["debits", data.bankAnalysis.summary.total_debits],
                   ["net", data.bankAnalysis.summary.net],
                   ["transactions", data.bankAnalysis.summary.transaction_count],
                 ] as const).map(([key, value]) => (
                   <div key={key} className="rounded-xl bg-muted/30 border p-4">
                     <p className="text-xs text-muted-foreground">{t(`dashboard.bankAnalysis.${key}`)}</p>
                     <p className="text-lg font-bold text-primary">
                       {Number(value).toLocaleString(language === "ar" ? "ar-JO" : "en-US")}
                       {key !== "transactions" && ` ${t("common.currency")}`}
                     </p>
                   </div>
                 ))}
               </div>
               <div className="grid md:grid-cols-2 gap-5">
                 <div className="rounded-xl border p-4">
                   <h4 className="font-bold mb-3">{t("dashboard.bankAnalysis.monthlyFlow")}</h4>
                   <div className="h-72">
                     <ResponsiveContainer width="100%" height="100%">
                       <BarChart data={data.bankAnalysis.monthly_breakdown}>
                         <CartesianGrid strokeDasharray="3 3" />
                         <XAxis dataKey="month" /><YAxis /><Tooltip /><Legend />
                         <Bar dataKey="credit" name={t("dashboard.bankAnalysis.credits")} fill="#17365D" />
                         <Bar dataKey="debit" name={t("dashboard.bankAnalysis.debits")} fill="#EAB308" />
                       </BarChart>
                     </ResponsiveContainer>
                   </div>
                 </div>
                 <div className="rounded-xl border p-4">
                   <h4 className="font-bold mb-3">{t("dashboard.bankAnalysis.categories")}</h4>
                   <div className="h-72">
                     <ResponsiveContainer width="100%" height="100%">
                       <RechartsPieChart>
                         <Pie data={data.bankAnalysis.category_breakdown} dataKey="amount" nameKey="category" innerRadius={50} outerRadius={85}>
                           {data.bankAnalysis.category_breakdown.map((_: unknown, index: number) => <Cell key={index} fill={CHART_COLORS[index % CHART_COLORS.length]} />)}
                         </Pie>
                         <Tooltip /><Legend />
                       </RechartsPieChart>
                     </ResponsiveContainer>
                   </div>
                 </div>
               </div>
             </>
           )}
           {!data.bankAnalysis && <div className="grid md:grid-cols-2 gap-5">
             <div className="rounded-xl border p-4 h-72">
               <ResponsiveContainer width="100%" height="100%">
                 <BarChart data={[
                   { name: t("dashboard.kpi.income"), value: data.monthlyIncome ?? 0 },
                   { name: t("dashboard.obligations.total"), value: data.monthlyObligations ?? 0 },
                   { name: t("dashboard.obligations.disposable"), value: data.disposableIncome ?? 0 },
                 ]}>
                   <CartesianGrid strokeDasharray="3 3" />
                   <XAxis dataKey="name" />
                   <YAxis />
                   <Tooltip />
                   <Bar dataKey="value" fill="#17365D" radius={[5, 5, 0, 0]} />
                 </BarChart>
               </ResponsiveContainer>
             </div>
             <div className="rounded-xl border p-4 h-72">
               <ResponsiveContainer width="100%" height="100%">
                 <RechartsPieChart>
                   <Pie data={data.budgetBreakdown ?? []} dataKey="amount" nameKey="category" innerRadius={50} outerRadius={85}>
                     {(data.budgetBreakdown ?? []).map((_: unknown, index: number) => <Cell key={index} fill={CHART_COLORS[index % CHART_COLORS.length]} />)}
                   </Pie>
                   <Tooltip />
                   <Legend />
                 </RechartsPieChart>
               </ResponsiveContainer>
             </div>
           </div>}

           <div>
              <h4 className="font-bold mb-3">{t("dashboard.dialogs.breakdown")}</h4>
             <div className="space-y-2">
               {(data.debtBreakdown ?? []).map((d: any, i: number) => (
                 <div key={i} className="flex justify-between items-center p-3 border rounded">
                   <span>{d.lenderName}</span>
                    <span className="font-bold">{d.remainingAmount.toLocaleString(language === "ar" ? "ar-JO" : "en-US")} {t("common.currency")}</span>
                 </div>
               ))}
             </div>
           </div>

           {(data.insights ?? []).length > 0 && (
             <div>
                <h4 className="font-bold mb-2">{t("dashboard.dialogs.insights")}</h4>
               <ul className="list-disc list-inside space-y-1 text-muted-foreground pr-4">
                 {(data.insights ?? []).map((insight: string, i: number) => <li key={i}>{insight}</li>)}
               </ul>
             </div>
           )}
         </div>
       )}
    </DialogWrapper>
  );
}

function AiAdviceDialog({ onClose }: { onClose: () => void }) {
  const { t } = useLanguage();
  const { profile } = useAuth();
  const summaryQuery = useGetFinancialSummary();
  const needIncome = (summaryQuery.data?.totalMonthlyIncome ?? 0) <= 0;
  const needObligations = summaryQuery.data?.dataSource !== "verified" && !profile?.manualObligationsDeclared;
  const [collectingObligations, setCollectingObligations] = useState(needIncome || needObligations);
  const advice = useGetAdvice();
  
  useEffect(() => {
    if (!collectingObligations) advice.mutate();
  }, []);

  return (
    <DialogWrapper title={t("dashboard.dialogs.advice")} isOpen={true} onClose={onClose}>
      {collectingObligations ? (
        <FinancialDetailsForm needIncome={needIncome} needObligations={needObligations}
          onSaved={() => { setCollectingObligations(false); advice.mutate(); }} />
      ) : advice.isPending ? <Loader2 className="w-8 h-8 animate-spin mx-auto text-secondary" /> :
       advice.isError ? <p className="text-destructive">{t("dashboard.error.generic")}</p> : 
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
  const { t } = useLanguage();
  const plan = useGetRestructurePlan();
  
  useState(() => {
    plan.mutate();
  });

  return (
    <DialogWrapper title={t("dashboard.dialogs.restructure")} isOpen={true} onClose={onClose}>
      {plan.isPending ? <Loader2 className="w-8 h-8 animate-spin mx-auto text-secondary" /> : 
       plan.isError ? <p className="text-destructive">{t("dashboard.error.generic")}</p> : 
       plan.data?.awaitingVerification ? <AwaitingVerificationNotice message={plan.data.message} /> :
       plan.data && (
         <div className="space-y-6">
           <div className="flex items-center justify-between p-4 bg-secondary/10 rounded-lg border border-secondary/20">
             <div className="text-center">
                <p className="text-sm text-muted-foreground">{t("dashboard.dialogs.current")}</p>
                <p className="text-xl font-bold line-through text-muted-foreground">{plan.data.currentMonthlyBurden} {t("common.currency")}</p>
             </div>
             <ArrowRightLeft className="w-6 h-6 text-secondary" />
             <div className="text-center">
                <p className="text-sm text-secondary font-bold">{t("dashboard.dialogs.target")}</p>
                <p className="text-2xl font-bold text-primary">{plan.data.targetMonthlyBurden} {t("common.currency")}</p>
             </div>
           </div>

           <p className="text-center font-medium">{t("dashboard.dialogs.duration", { months: plan.data.months ?? 0 })}</p>

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
  const { t, language } = useLanguage();
  const req = useRequestConsolidation();
  
  useState(() => {
    req.mutate();
  });

  return (
    <DialogWrapper title={t("dashboard.dialogs.consolidation")} isOpen={true} onClose={onClose}>
      {req.isPending ? <Loader2 className="w-8 h-8 animate-spin mx-auto text-secondary" /> : 
       req.isError ? <p className="text-destructive">{t("dashboard.error.generic")}</p> : 
       req.data?.awaitingVerification ? <AwaitingVerificationNotice message={req.data.message} /> :
       req.data && (
         <div className="text-center py-6 space-y-6">
           <div className="w-16 h-16 bg-green-100 text-green-600 rounded-full flex items-center justify-center mx-auto">
             <CheckCircle2 className="w-8 h-8" />
           </div>
           
           <div>
              <h3 className="text-xl font-bold mb-2">{t("dashboard.dialogs.initialSuccess")}</h3>
              <p className="text-muted-foreground">{t("dashboard.dialogs.requestNumber", { id: req.data.id ?? 0 })}</p>
           </div>
           
           <div className="bg-muted/30 p-6 rounded-xl inline-block text-right border">
              <p className="mb-2"><strong>{t("dashboard.dialogs.institutions")}</strong> {req.data.institutionsIncluded}</p>
              <p><strong>{t("dashboard.dialogs.estimated")}</strong> {(req.data.estimatedConsolidatedMonthlyPayment ?? 0).toLocaleString(language === "ar" ? "ar-JO" : "en-US")} {t("common.currency")} / {language === "ar" ? "شهر" : "month"}</p>
           </div>
           
            <p className="text-sm text-muted-foreground">{t("dashboard.dialogs.contact")}</p>
         </div>
       )}
    </DialogWrapper>
  );
}

function EligibilityDialog({ onClose }: { onClose: () => void }) {
  const { t, language } = useLanguage();
  const check = useAssessLoanEligibility();
  
  useEffect(() => {
    check.mutate();
  }, []);

  return (
    <DialogWrapper title={t("dashboard.dialogs.eligibility")} isOpen={true} onClose={onClose}>
      {check.isPending ? <Loader2 className="w-8 h-8 animate-spin mx-auto text-secondary" /> : 
       check.isError ? <p className="text-destructive">{t("dashboard.error.generic")}</p> : 
       check.data && (
         <div className="space-y-6">
           {/* Credit Score */}
           <div className="p-6 rounded-xl border text-center bg-primary/5 border-primary/10">
              <p className="text-sm text-muted-foreground mb-2">{t("dashboard.dialogs.creditScore")}</p>
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
                {check.data.eligible ? t("dashboard.dialogs.eligible") : t("dashboard.dialogs.notEligible")}
             </h3>
             <p className="opacity-90">{check.data.recommendation}</p>
           </div>

           {check.data.eligible && (
             <div className="grid grid-cols-2 gap-4">
               <div className="p-4 bg-muted/30 rounded-lg text-center border">
                  <p className="text-sm text-muted-foreground">{t("dashboard.application.recommended")}</p>
                  <p className="text-2xl font-bold text-primary">{check.data.recommendedAmount?.toLocaleString(language === "ar" ? "ar-JO" : "en-US")} {t("common.currency")}</p>
               </div>
               <div className="p-4 bg-muted/30 rounded-lg text-center border">
                  <p className="text-sm text-muted-foreground">{t("dashboard.dialogs.expectedInstallment")}</p>
                  <p className="text-2xl font-bold text-secondary">{check.data.monthlyInstallment?.toLocaleString(language === "ar" ? "ar-JO" : "en-US")} {t("common.currency")}</p>
               </div>
             </div>
           )}
         </div>
       )}
    </DialogWrapper>
  );
}
