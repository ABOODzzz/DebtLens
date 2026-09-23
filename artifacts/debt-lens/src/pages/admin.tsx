import { useState } from "react";
import {
  useListAdminUsers,
  useSubmitKycDecision,
  getListAdminUsersQueryKey,
  useGetAdminUserDetail,
  useListGuarantorRequests,
  getListGuarantorRequestsQueryKey,
  useGetGuarantorInsight,
  useSubmitGuarantorDecision,
  useReviseGuarantorDecision,
  useListLoanApplications,
  getListLoanApplicationsQueryKey,
  useSubmitLoanApplicationDecision,
  useReviseLoanApplicationDecision,
} from "@workspace/api-client-react";
import type {
  AdminLoanApplicationSummary,
  GuarantorReviseInputNewStatus,
  LoanApplicationReviseInputNewStatus,
} from "@workspace/api-client-react";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Loader2, UserCheck, UserX, AlertCircle, Eye, ShieldCheck, Sparkles, ImageOff, Wallet, RotateCcw, History, Download } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

export default function AdminPage() {
  return (
    <div className="flex-1 container mx-auto p-4 md:p-8">
      <h1 className="text-2xl font-bold text-primary mb-6">لوحة الإدارة</h1>
      <Tabs defaultValue="users" className="w-full">
        <TabsList className="mb-6">
          <TabsTrigger value="users">العملاء</TabsTrigger>
          <TabsTrigger value="guarantors">طلبات الكفيل الرقمي</TabsTrigger>
          <TabsTrigger value="loans">طلبات التمويل</TabsTrigger>
        </TabsList>
        <TabsContent value="users">
          <UsersTab />
        </TabsContent>
        <TabsContent value="guarantors">
          <GuarantorRequestsTab />
        </TabsContent>
        <TabsContent value="loans">
          <LoanApplicationsTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// --- Users tab: list + KYC decisions + detail dialog ---
function UsersTab() {
  const queryClient = useQueryClient();
  const usersQuery = useListAdminUsers();
  const decisionMutation = useSubmitKycDecision();
  const [pendingUid, setPendingUid] = useState<string | null>(null);
  const [detailUid, setDetailUid] = useState<string | null>(null);
  const [rejectTarget, setRejectTarget] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const { toast } = useToast();

  const handleApprove = async (uid: string) => {
    setPendingUid(uid);
    try {
      await decisionMutation.mutateAsync({ data: { uid, decision: "approved" } });
      queryClient.invalidateQueries({ queryKey: getListAdminUsersQueryKey() });
    } catch (error) {
      console.error("Error updating KYC decision", error);
      toast({ variant: "destructive", title: "فشل حفظ القرار", description: "تعذر تحديث حالة المستخدم. يرجى المحاولة مرة أخرى." });
    } finally {
      setPendingUid(null);
    }
  };

  const handleReject = async () => {
    if (!rejectTarget) return;
    setPendingUid(rejectTarget);
    try {
      await decisionMutation.mutateAsync({ data: { uid: rejectTarget, decision: "rejected", note: rejectReason.trim() || null } });
      queryClient.invalidateQueries({ queryKey: getListAdminUsersQueryKey() });
      setRejectTarget(null);
      setRejectReason("");
    } catch (error) {
      console.error("Error updating KYC decision", error);
      toast({ variant: "destructive", title: "فشل حفظ القرار", description: "تعذر تحديث حالة المستخدم. يرجى المحاولة مرة أخرى." });
    } finally {
      setPendingUid(null);
    }
  };

  if (usersQuery.isLoading) {
    return <div className="flex items-center justify-center py-24"><Loader2 className="w-8 h-8 animate-spin" /></div>;
  }

  if (usersQuery.isError || !usersQuery.data) {
    return (
      <div className="flex items-center justify-center p-8 text-center text-destructive">
        <div>
          <AlertCircle className="w-12 h-12 mx-auto mb-4" />
          <p>حدث خطأ أثناء تحميل بيانات المستخدمين.</p>
        </div>
      </div>
    );
  }

  const { users, user_count } = usersQuery.data;

  return (
    <div>
      <div className="flex justify-end mb-4">
        <div className="text-sm bg-primary/10 text-primary px-3 py-1 rounded-full font-medium">
          إجمالي المستخدمين: {user_count}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4">
        {users.map(user => (
          <Card key={user.uid} className="overflow-hidden">
            <CardContent className="p-0">
              <div className="flex flex-col md:flex-row items-center justify-between p-4 gap-4">

                <div className="flex-1 w-full grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <p className="text-xs text-muted-foreground">الاسم</p>
                    <p className="font-bold truncate">{user.name || "غير متوفر"}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">الحالة</p>
                    <span className={`text-xs px-2 py-1 rounded-full font-medium ${
                      user.review_status === 'approved' ? 'bg-green-100 text-green-700' :
                      user.review_status === 'rejected' ? 'bg-red-100 text-red-700' :
                      user.review_status === 'pending' ? 'bg-yellow-100 text-yellow-700' :
                      'bg-gray-100 text-gray-700'
                    }`}>
                      {user.review_status === 'approved' ? 'مقبول - موثّق' :
                       user.review_status === 'rejected' ? 'مرفوض' :
                       user.review_status === 'pending' ? 'قيد المراجعة' : 'غير مكتمل'}
                    </span>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">نسبة عبء الدين</p>
                    <p className="font-medium text-sm">
                      {user.debt_to_income_percentage != null ? `${Math.round(user.debt_to_income_percentage)}%` : "-"}
                      {user.stacking_flag && <span className="text-destructive font-bold"> (تكديس ديون)</span>}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">آخر تحديث</p>
                    <p className="font-medium text-sm truncate dir-ltr">{user.updated_at ? new Date(user.updated_at).toLocaleDateString() : "-"}</p>
                  </div>
                </div>

                <div className="flex gap-2 w-full md:w-auto shrink-0 border-t md:border-t-0 md:border-r border-border pt-4 md:pt-0 md:pr-4">
                  <Button size="sm" variant="outline" onClick={() => setDetailUid(user.uid)}>
                    <Eye className="w-4 h-4 ml-1" /> التفاصيل
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="bg-green-50 text-green-700 hover:bg-green-100 hover:text-green-800 border-green-200"
                    disabled={user.review_status === 'approved' || (decisionMutation.isPending && pendingUid === user.uid)}
                    onClick={() => handleApprove(user.uid)}
                  >
                    {decisionMutation.isPending && pendingUid === user.uid ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <><UserCheck className="w-4 h-4 ml-1" /> قبول</>
                    )}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="bg-red-50 text-red-700 hover:bg-red-100 hover:text-red-800 border-red-200"
                    disabled={user.review_status === 'rejected' || (decisionMutation.isPending && pendingUid === user.uid)}
                    onClick={() => { setRejectTarget(user.uid); setRejectReason(""); }}
                  >
                    <UserX className="w-4 h-4 ml-1" /> رفض
                  </Button>
                </div>

              </div>
            </CardContent>
          </Card>
        ))}
        {users.length === 0 && (
          <div className="text-center py-12 text-muted-foreground">لا يوجد مستخدمين مسجلين بعد.</div>
        )}
      </div>

      {detailUid && <UserDetailDialog uid={detailUid} onClose={() => setDetailUid(null)} />}

      <Dialog open={!!rejectTarget} onOpenChange={(open) => !open && setRejectTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>سبب الرفض</DialogTitle>
            <DialogDescription>سيظهر هذا السبب للعميل حتى يتمكن من تصحيح بياناته وإعادة التقديم.</DialogDescription>
          </DialogHeader>
          <Textarea
            placeholder="مثال: صورة الهوية غير واضحة، يرجى رفع صورة أوضح"
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            rows={4}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectTarget(null)}>إلغاء</Button>
            <Button
              variant="destructive"
              disabled={decisionMutation.isPending}
              onClick={handleReject}
            >
              {decisionMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : "تأكيد الرفض"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function PhotoTile({ label, url }: { label: string; url: string | null | undefined }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground mb-1">{label}</p>
      {url ? (
        <img src={url} alt={label} className="w-full h-40 object-cover rounded-lg border" />
      ) : (
        <div className="w-full h-40 rounded-lg border bg-muted/30 flex items-center justify-center text-muted-foreground">
          <ImageOff className="w-6 h-6" />
        </div>
      )}
    </div>
  );
}

function UserDetailDialog({ uid, onClose }: { uid: string; onClose: () => void }) {
  const detail = useGetAdminUserDetail(uid);

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{detail.data?.name || "تفاصيل العميل"}</DialogTitle>
          <DialogDescription dir="ltr" className="text-xs text-left">{uid}</DialogDescription>
        </DialogHeader>

        {detail.isLoading ? (
          <div className="flex justify-center py-12"><Loader2 className="w-8 h-8 animate-spin" /></div>
        ) : detail.isError || !detail.data ? (
          <p className="text-destructive text-center py-8">حدث خطأ أثناء تحميل بيانات العميل.</p>
        ) : (
          <div className="space-y-6">
            <div>
              <h4 className="font-bold mb-3">صور التحقق من الهوية</h4>
              <div className="grid grid-cols-3 gap-3">
                <PhotoTile label="الهوية - الوجه الأمامي" url={detail.data.kyc.id_front_url} />
                <PhotoTile label="الهوية - الوجه الخلفي" url={detail.data.kyc.id_back_url} />
                <PhotoTile label="الصورة الشخصية (السيلفي)" url={detail.data.kyc.selfie_url} />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="p-3 bg-muted/30 rounded-lg">
                <p className="text-xs text-muted-foreground">الاسم المُدخل</p>
                <p className="font-medium">{detail.data.kyc.typed_full_name || "-"}</p>
              </div>
              <div className="p-3 bg-muted/30 rounded-lg">
                <p className="text-xs text-muted-foreground">الاسم المستخرج من الهوية</p>
                <p className="font-medium">{detail.data.kyc.extracted_full_name || "-"}</p>
              </div>
              <div className="p-3 bg-muted/30 rounded-lg">
                <p className="text-xs text-muted-foreground">الرقم الوطني المُدخل</p>
                <p className="font-medium dir-ltr">{detail.data.kyc.typed_national_id || "-"}</p>
              </div>
              <div className="p-3 bg-muted/30 rounded-lg">
                <p className="text-xs text-muted-foreground">الرقم الوطني المستخرج</p>
                <p className="font-medium dir-ltr">{detail.data.kyc.extracted_national_id || "-"}</p>
              </div>
              <div className="p-3 bg-muted/30 rounded-lg">
                <p className="text-xs text-muted-foreground">تطابق الوجه</p>
                <p className="font-medium">{detail.data.kyc.face_match || "-"}</p>
              </div>
              <div className="p-3 bg-muted/30 rounded-lg">
                <p className="text-xs text-muted-foreground">درجة الثقة</p>
                <p className="font-medium">{detail.data.kyc.confidence || "-"}</p>
              </div>
            </div>
            {detail.data.kyc.ai_reason && (
              <p className="text-sm text-muted-foreground bg-primary/5 p-3 rounded-lg">{detail.data.kyc.ai_reason}</p>
            )}

            <div>
              <h4 className="font-bold mb-3">الملف المالي</h4>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <div className="p-3 bg-muted/30 rounded-lg">
                  <p className="text-xs text-muted-foreground">الدخل الشهري</p>
                  <p className="font-medium">{detail.data.financial.monthly_income?.toLocaleString()} د.أ</p>
                </div>
                <div className="p-3 bg-muted/30 rounded-lg">
                  <p className="text-xs text-muted-foreground">حالة التوظيف</p>
                  <p className="font-medium">{detail.data.financial.employment_status || "-"}</p>
                </div>
                <div className="p-3 bg-muted/30 rounded-lg">
                  <p className="text-xs text-muted-foreground">جهة العمل</p>
                  <p className="font-medium">{detail.data.financial.employer_name || "-"}</p>
                </div>
                <div className="p-3 bg-muted/30 rounded-lg">
                  <p className="text-xs text-muted-foreground">نسبة عبء الدين</p>
                  <p className="font-medium">
                    {detail.data.financial.debt_to_income_percentage != null ? `${Math.round(detail.data.financial.debt_to_income_percentage)}%` : "-"}
                  </p>
                </div>
                <div className="p-3 bg-muted/30 rounded-lg">
                  <p className="text-xs text-muted-foreground">عدد الكشوفات</p>
                  <p className="font-medium">{detail.data.financial.statement_count}</p>
                </div>
                <div className="p-3 bg-muted/30 rounded-lg">
                  <p className="text-xs text-muted-foreground">مصدر البيانات</p>
                  <p className="font-medium">{detail.data.financial.data_source === "verified" ? "موثّق من كشوفات" : "مُصرَّح ذاتياً"}</p>
                </div>
              </div>
            </div>

            {(detail.data.financial.bank_accounts?.length ?? 0) > 0 && (
              <div>
                <h4 className="font-bold mb-2">الحسابات البنكية</h4>
                <div className="space-y-2">
                  {detail.data.financial.bank_accounts!.map((acc: any, i: number) => (
                    <div key={i} className="p-3 bg-muted/30 rounded-lg text-sm flex justify-between">
                      <span>{acc.bankName}</span>
                      <span className="dir-ltr text-muted-foreground">{acc.accountNumber}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {(detail.data.financial.self_reported_debts?.length ?? 0) > 0 && (
              <div>
                <h4 className="font-bold mb-2">الديون المُصرَّح بها ذاتياً</h4>
                <div className="space-y-2">
                  {detail.data.financial.self_reported_debts!.map((debt: any, i: number) => (
                    <div key={i} className="p-3 bg-muted/30 rounded-lg text-sm flex justify-between">
                      <span>{debt.lenderName}</span>
                      <span className="font-medium">{debt.remainingAmount?.toLocaleString()} د.أ</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {detail.data.statements.length > 0 && (
              <div>
                <h4 className="font-bold mb-2">الكشوفات المرفوعة</h4>
                <div className="space-y-2">
                  {detail.data.statements.map((s) => (
                    <div key={s.statement_id} className="p-3 bg-muted/30 rounded-lg text-sm flex justify-between items-center">
                      <span>{s.institution_name} ({s.statement_type})</span>
                      <span className="font-medium">{s.remaining_balance?.toLocaleString()} د.أ متبقي</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {detail.data.review_status === 'rejected' && detail.data.review_reason && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800">
                سبب الرفض: {detail.data.review_reason}
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

// --- Guarantor requests tab: admin makes the final call, backed by AI ---
function riskTierClass(tier: string) {
  if (tier === "منخفض") return "bg-green-100 text-green-700";
  if (tier === "متوسط") return "bg-yellow-100 text-yellow-700";
  return "bg-red-100 text-red-700";
}

function guarantorDecisionStatusLabel(status: string) {
  if (status === "awaiting_admin_review") return "بانتظار قرار الإدارة";
  if (status === "approved") return "موافق عليه";
  if (status === "rejected") return "مرفوض";
  return status;
}
function GuarantorRequestsTab() {
  const queryClient = useQueryClient();
  const requestsQuery = useListGuarantorRequests();
  const insightMutation = useGetGuarantorInsight();
  const decisionMutation = useSubmitGuarantorDecision();
  const reviseMutation = useReviseGuarantorDecision();
  const [insightByRelationship, setInsightByRelationship] = useState<Record<string, any>>({});
  const [activeRelationship, setActiveRelationship] = useState<string | null>(null);
  const [reviseTarget, setReviseTarget] = useState<string | null>(null);
  const [reviseNewStatus, setReviseNewStatus] = useState<GuarantorReviseInputNewStatus>("rejected");
  const [reviseReason, setReviseReason] = useState("");
  const [expandedHistory, setExpandedHistory] = useState<Record<string, boolean>>({});
  const { toast } = useToast();

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: getListGuarantorRequestsQueryKey() });
    queryClient.invalidateQueries({ queryKey: getListLoanApplicationsQueryKey() });
  };

  const handleGetInsight = async (relationshipId: string) => {
    setActiveRelationship(relationshipId);
    try {
      const result = await insightMutation.mutateAsync({ data: { relationship_id: relationshipId } });
      setInsightByRelationship((prev) => ({ ...prev, [relationshipId]: result }));
    } catch (error) {
      toast({ variant: "destructive", title: "تعذر توليد التحليل", description: "يرجى المحاولة مرة أخرى." });
    } finally {
      setActiveRelationship(null);
    }
  };

  const handleDecision = async (relationshipId: string, decision: "approved" | "rejected") => {
    setActiveRelationship(relationshipId);
    try {
      await decisionMutation.mutateAsync({ data: { relationship_id: relationshipId, decision } });
      invalidate();
    } catch (error) {
      toast({ variant: "destructive", title: "تعذر حفظ القرار", description: "يرجى المحاولة مرة أخرى." });
    } finally {
      setActiveRelationship(null);
    }
  };

  const openRevise = (relationshipId: string, currentStatus: string) => {
    setReviseTarget(relationshipId);
    setReviseNewStatus(currentStatus === "approved" ? "rejected" : "approved");
    setReviseReason("");
  };

  const handleRevise = async () => {
    if (!reviseTarget) return;
    if (!reviseReason.trim()) {
      toast({ variant: "destructive", title: "السبب مطلوب", description: "يرجى توضيح سبب تعديل القرار." });
      return;
    }
    setActiveRelationship(reviseTarget);
    try {
      await reviseMutation.mutateAsync({
        data: { relationship_id: reviseTarget, new_status: reviseNewStatus, reason: reviseReason.trim() },
      });
      invalidate();
      setReviseTarget(null);
      setReviseReason("");
    } catch (error) {
      toast({
        variant: "destructive",
        title: "تعذر تعديل قرار الكفالة",
        description: "قد تكون فترة التعديل المسموح بها قد انتهت، أو تغيّرت حالة الطلب. يرجى تحديث الصفحة والمحاولة مرة أخرى.",
      });
    } finally {
      setActiveRelationship(null);
    }
  };

  if (requestsQuery.isLoading) {
    return <div className="flex items-center justify-center py-24"><Loader2 className="w-8 h-8 animate-spin" /></div>;
  }

  if (requestsQuery.isError || !requestsQuery.data) {
    return (
      <div className="flex items-center justify-center p-8 text-center text-destructive">
        <AlertCircle className="w-12 h-12 mx-auto mb-4" />
        <p>حدث خطأ أثناء تحميل طلبات الكفالة.</p>
      </div>
    );
  }

  const { requests, awaiting_count } = requestsQuery.data;

  return (
    <div>
      <div className="flex justify-end mb-4">
        <div className="text-sm bg-blue-100 text-blue-700 px-3 py-1 rounded-full font-medium">
          بانتظار المراجعة: {awaiting_count}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4">
        {requests.map((req) => {
          const insight = insightByRelationship[req.id];
          const history = req.decision_history ?? [];
          const busy = activeRelationship === req.id && (insightMutation.isPending || decisionMutation.isPending || reviseMutation.isPending);
          return (
            <Card key={req.id}>
              <CardContent className="p-4 space-y-4">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-2">
                    <ShieldCheck className="w-5 h-5 text-secondary" />
                    <span className="font-bold">{req.requester_name}</span>
                    <span className="text-muted-foreground text-sm">يطلب كفالة من</span>
                    <span className="font-bold">{req.guarantor_name || "-"}</span>
                  </div>
                  <Badge variant={req.status === 'approved' ? 'default' : req.status === 'rejected' ? 'destructive' : 'secondary'}>
                    {guarantorDecisionStatusLabel(req.status)}
                  </Badge>
                </div>

                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div className="p-3 bg-muted/30 rounded-lg">
                    <p className="text-xs text-muted-foreground mb-1">مقدّم الطلب: {req.requester_name}</p>
                    <p>نسبة عبء الدين: {req.requester_debt_to_income_percentage != null ? `${Math.round(req.requester_debt_to_income_percentage)}%` : "-"}</p>
                    {req.requester_stacking_flag && <p className="text-destructive font-medium">تكديس ديون</p>}
                  </div>
                  <div className="p-3 bg-muted/30 rounded-lg">
                    <p className="text-xs text-muted-foreground mb-1">الكفيل: {req.guarantor_name}</p>
                    <p>نسبة عبء الدين: {req.guarantor_debt_to_income_percentage != null ? `${Math.round(req.guarantor_debt_to_income_percentage)}%` : "-"}</p>
                    {req.guarantor_stacking_flag && <p className="text-destructive font-medium">تكديس ديون</p>}
                    {req.guarantor_active_guarantees_count != null && req.guarantor_max_concurrent != null && (
                      <p className="text-muted-foreground">يكفل حالياً {req.guarantor_active_guarantees_count} / {req.guarantor_max_concurrent}</p>
                    )}
                  </div>
                </div>

                <p className="text-xs text-muted-foreground">الحد الأقصى للكفالة: {req.max_amount?.toLocaleString()} د.أ</p>

                {insight && (
                  <div className="p-3 rounded-lg border bg-primary/5 space-y-2">
                    <div className="flex items-center gap-2">
                      <Sparkles className="w-4 h-4 text-secondary" />
                      <span className="text-sm font-bold">تحليل الذكاء الاصطناعي</span>
                      <span className={`text-xs px-2 py-1 rounded-full font-medium ${riskTierClass(insight.risk_tier)}`}>{insight.risk_tier}</span>
                      <span className={`text-xs px-2 py-1 rounded-full font-medium ${insight.recommendation === 'approve' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                        توصية: {insight.recommendation === 'approve' ? 'موافقة' : 'رفض'}
                      </span>
                    </div>
                    {insight.concerns.length > 0 && (
                      <ul className="list-disc list-inside text-sm text-muted-foreground pr-2">
                        {insight.concerns.map((c: string, i: number) => <li key={i}>{c}</li>)}
                      </ul>
                    )}
                    <p className="text-sm">{insight.notes}</p>
                  </div>
                )}

                {req.status === 'awaiting_admin_review' && (
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="outline" disabled={busy} onClick={() => handleGetInsight(req.id)}>
                      {busy && insightMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin ml-1" /> : <Sparkles className="w-4 h-4 ml-1" />}
                      تحليل بالذكاء الاصطناعي
                    </Button>
                    <Button
                      size="sm"
                      className="bg-green-600 hover:bg-green-700"
                      disabled={busy}
                      onClick={() => handleDecision(req.id, "approved")}
                    >
                      {busy && decisionMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin ml-1" /> : <UserCheck className="w-4 h-4 ml-1" />}
                      الموافقة على الكفالة
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      disabled={busy}
                      onClick={() => handleDecision(req.id, "rejected")}
                    >
                      {busy && decisionMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin ml-1" /> : <UserX className="w-4 h-4 ml-1" />}
                      رفض الكفالة
                    </Button>
                  </div>
                )}

                {(req.status === 'approved' || req.status === 'rejected') && (
                  <div className="space-y-3">
                    <div className="flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={busy}
                        onClick={() => openRevise(req.id, req.status)}
                      >
                        {busy && reviseMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin ml-1" /> : <RotateCcw className="w-4 h-4 ml-1" />}
                        تعديل القرار
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setExpandedHistory((previous) => ({
                          ...previous,
                          [req.id]: !previous[req.id],
                        }))}
                      >
                        <History className="w-4 h-4 ml-1" />
                        {expandedHistory[req.id] ? "إخفاء سجل القرارات" : "عرض سجل القرارات"}
                      </Button>
                    </div>
                    {expandedHistory[req.id] && (
                      <div className="rounded-lg border bg-muted/20 p-3 space-y-3">
                        <p className="text-sm font-bold">سجل قرارات الإدارة</p>
                        {history.length === 0 ? (
                          <p className="text-sm text-muted-foreground">لا يوجد سجل محفوظ لهذا القرار.</p>
                        ) : (
                          <div className="space-y-3">
                            {history.slice().reverse().map((entry, index) => (
                              <div key={`${entry.timestamp}-${entry.admin_uid}-${index}`} className="border-r-2 border-primary/30 pr-3 text-sm">
                                <div className="flex flex-wrap items-center gap-2">
                                  <Badge variant={entry.new_status === "approved" ? "default" : "destructive"}>
                                    {guarantorDecisionStatusLabel(entry.new_status)}
                                  </Badge>
                                  <span className="text-xs text-muted-foreground">
                                    {formatGuarantorDecisionTimestamp(entry.timestamp)}
                                  </span>
                                </div>
                                <p className="mt-1 text-muted-foreground">
                                  من {guarantorDecisionStatusLabel(entry.previous_status)} إلى {guarantorDecisionStatusLabel(entry.new_status)}
                                </p>
                                {entry.reason && <p className="mt-1">السبب: {entry.reason}</p>}
                                <p className="mt-1 text-xs text-muted-foreground" dir="ltr">
                                  المسؤول: {entry.admin_uid}
                                </p>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
        {requests.length === 0 && (
          <div className="text-center py-12 text-muted-foreground">لا يوجد طلبات كفالة رقمية حتى الآن.</div>
        )}
      </div>

      <Dialog open={reviseTarget != null} onOpenChange={(open) => !open && setReviseTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>تعديل قرار الكفالة الرقمية</DialogTitle>
            <DialogDescription>
              يُستخدم هذا لتصحيح قرار حديث اتُّخذ بالخطأ أو بناءً على معلومات غير محدّثة. سيتم إشعار مقدّم الطلب
              والكفيل بالتعديل، ولا يمكن تعديل قرار مرّت عليه أكثر من ١٤ يومًا.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <p className="text-sm font-medium mb-1">الحالة الجديدة</p>
              <Select value={reviseNewStatus} onValueChange={(value) => setReviseNewStatus(value as GuarantorReviseInputNewStatus)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="approved">الموافقة</SelectItem>
                  <SelectItem value="rejected">الرفض</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <p className="text-sm font-medium mb-1">سبب التعديل</p>
              <Textarea
                placeholder="مثال: تم اتخاذ القرار بناءً على معلومات غير محدّثة."
                value={reviseReason}
                onChange={(e) => setReviseReason(e.target.value)}
                rows={4}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setReviseTarget(null)}>إلغاء</Button>
            <Button disabled={reviseMutation.isPending} onClick={handleRevise}>
              {reviseMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : "تأكيد التعديل"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// --- Loan applications tab: admin makes the final disbursement call ---
function loanApplicationStatusBadge(statusValue: string) {
  if (statusValue === 'approved') return { variant: 'default' as const, label: 'تمت الموافقة' };
  if (statusValue === 'admin_rejected') return { variant: 'destructive' as const, label: 'مرفوض' };
  return { variant: 'secondary' as const, label: 'بانتظار القرار النهائي' };
}

function loanDecisionHistoryLabel(decision: string) {
  if (decision === "approved") return "موافقة نهائية";
  if (decision === "rejected") return "رفض";
  return "إعادة للمراجعة";
}

function csvCell(value: string | number | null | undefined) {
  return `"${String(value ?? "").replace(/"/g, '""')}"`;
}

function exportLoanDecisionHistory(application: AdminLoanApplicationSummary) {
  const rows = [
    ["application_id", "customer_name", "decision", "reason", "admin_uid", "created_at"],
    ...application.decision_history.map((entry) => [
      application.id,
      application.customer_name,
      entry.decision,
      entry.reason,
      entry.admin_uid,
      entry.created_at,
    ]),
  ];
  const csv = `\ufeff${rows.map((row) => row.map(csvCell).join(",")).join("\r\n")}`;
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const downloadUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = downloadUrl;
  link.download = `loan-decision-history-${application.id}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(downloadUrl);
}

function LoanApplicationsTab() {
  const queryClient = useQueryClient();
  const applicationsQuery = useListLoanApplications();
  const decisionMutation = useSubmitLoanApplicationDecision();
  const reviseMutation = useReviseLoanApplicationDecision();
  const [activeApplicationId, setActiveApplicationId] = useState<number | null>(null);
  const [rejectTarget, setRejectTarget] = useState<number | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [reviseTarget, setReviseTarget] = useState<number | null>(null);
  const [reviseNewStatus, setReviseNewStatus] = useState<LoanApplicationReviseInputNewStatus>("submitted");
  const [reviseReason, setReviseReason] = useState("");
  const { toast } = useToast();

  const invalidate = () => queryClient.invalidateQueries({ queryKey: getListLoanApplicationsQueryKey() });

  const handleApprove = async (applicationId: number) => {
    setActiveApplicationId(applicationId);
    try {
      await decisionMutation.mutateAsync({ data: { application_id: applicationId, decision: "approved" } });
      invalidate();
    } catch (error) {
      toast({ variant: "destructive", title: "تعذر حفظ القرار", description: "يرجى المحاولة مرة أخرى." });
    } finally {
      setActiveApplicationId(null);
    }
  };

  const handleReject = async () => {
    if (rejectTarget == null) return;
    setActiveApplicationId(rejectTarget);
    try {
      await decisionMutation.mutateAsync({
        data: { application_id: rejectTarget, decision: "rejected", reason: rejectReason.trim() || null },
      });
      invalidate();
      setRejectTarget(null);
      setRejectReason("");
    } catch (error) {
      toast({ variant: "destructive", title: "تعذر حفظ القرار", description: "يرجى المحاولة مرة أخرى." });
    } finally {
      setActiveApplicationId(null);
    }
  };

  const openRevise = (applicationId: number, currentStatus: string) => {
    setReviseTarget(applicationId);
    setReviseNewStatus(currentStatus === "approved" ? "rejected" : "approved");
    setReviseReason("");
  };

  const handleRevise = async () => {
    if (reviseTarget == null) return;
    if (!reviseReason.trim()) {
      toast({ variant: "destructive", title: "السبب مطلوب", description: "يرجى توضيح سبب تعديل القرار." });
      return;
    }
    setActiveApplicationId(reviseTarget);
    try {
      await reviseMutation.mutateAsync({
        data: { application_id: reviseTarget, new_status: reviseNewStatus, reason: reviseReason.trim() },
      });
      invalidate();
      setReviseTarget(null);
      setReviseReason("");
    } catch (error) {
      toast({
        variant: "destructive",
        title: "تعذر تعديل القرار",
        description: "قد تكون فترة التعديل المسموح بها قد انتهت، أو تغيّرت حالة الطلب. يرجى تحديث الصفحة والمحاولة مرة أخرى.",
      });
    } finally {
      setActiveApplicationId(null);
    }
  };

  if (applicationsQuery.isLoading) {
    return <div className="flex items-center justify-center py-24"><Loader2 className="w-8 h-8 animate-spin" /></div>;
  }

  if (applicationsQuery.isError || !applicationsQuery.data) {
    return (
      <div className="flex items-center justify-center p-8 text-center text-destructive">
        <AlertCircle className="w-12 h-12 mx-auto mb-4" />
        <p>حدث خطأ أثناء تحميل طلبات التمويل.</p>
      </div>
    );
  }

  const { applications, awaiting_count } = applicationsQuery.data;

  return (
    <div>
      <div className="flex justify-end mb-4">
        <div className="text-sm bg-blue-100 text-blue-700 px-3 py-1 rounded-full font-medium">
          بانتظار القرار النهائي: {awaiting_count}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4">
        {applications.map((app) => {
          const badge = loanApplicationStatusBadge(app.status);
          const busy = activeApplicationId === app.id && decisionMutation.isPending;
          return (
            <Card key={app.id}>
              <CardContent className="p-4 space-y-4">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-2">
                    <Wallet className="w-5 h-5 text-secondary" />
                    <span className="font-bold">{app.customer_name}</span>
                    {app.customer_national_id && (
                      <span className="text-xs text-muted-foreground dir-ltr">{app.customer_national_id}</span>
                    )}
                  </div>
                  <Badge variant={badge.variant}>{badge.label}</Badge>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                  <div className="p-3 bg-muted/30 rounded-lg">
                    <p className="text-xs text-muted-foreground mb-1">المبلغ المطلوب</p>
                    <p className="font-bold">{app.requested_amount.toLocaleString()} د.أ</p>
                  </div>
                  <div className="p-3 bg-muted/30 rounded-lg">
                    <p className="text-xs text-muted-foreground mb-1">المبلغ الموصى به</p>
                    <p className="font-bold">{app.recommended_amount != null ? `${app.recommended_amount.toLocaleString()} د.أ` : "-"}</p>
                  </div>
                  <div className="p-3 bg-muted/30 rounded-lg">
                    <p className="text-xs text-muted-foreground mb-1">الدرجة الائتمانية</p>
                    <p className="font-bold">{app.credit_score ?? "-"}</p>
                  </div>
                  <div className="p-3 bg-muted/30 rounded-lg">
                    <p className="text-xs text-muted-foreground mb-1">مستوى المخاطرة</p>
                    <p className="font-bold">{app.risk_tier ?? "-"}</p>
                  </div>
                </div>

                <p className="text-xs text-muted-foreground">الغرض: {app.purpose}</p>
                {app.guarantor_relationship_id && (
                  <p className="text-xs text-blue-700 bg-blue-50 border border-blue-200 rounded-lg p-2">
                    مدعوم بكفيل رقمي مُوافَق عليه (معرّف الكفالة: {app.guarantor_relationship_id})
                  </p>
                )}
                <p className="text-sm text-muted-foreground leading-relaxed">{app.recommendation}</p>

                {app.status === 'admin_rejected' && app.admin_decision_reason && (
                  <p className="text-sm text-red-800 bg-red-50 border border-red-200 rounded-lg p-2">
                    سبب الرفض: {app.admin_decision_reason}
                  </p>
                )}

                {app.decision_history.length > 0 && (
                  <div className="border border-slate-200 rounded-lg p-3 space-y-3">
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                        <History className="w-4 h-4" />
                        سجل قرارات الإدارة
                      </div>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => exportLoanDecisionHistory(app)}
                      >
                        <Download className="w-4 h-4 ml-1" />
                        تصدير السجل
                      </Button>
                    </div>
                    <div className="space-y-2">
                      {app.decision_history.slice().reverse().map((entry, index) => (
                        <div key={entry.id} className="rounded-md bg-slate-50 p-2 text-sm">
                          <div className="flex items-center justify-between gap-2 flex-wrap">
                            <span className="font-medium">
                              {index === app.decision_history.length - 1 ? "القرار الأول" : "تعديل القرار"}:{" "}
                              {loanDecisionHistoryLabel(entry.decision)}
                            </span>
                            <span className="text-xs text-muted-foreground">
                              {new Date(entry.created_at).toLocaleString("ar-JO", {
                                dateStyle: "medium",
                                timeStyle: "short",
                              })}
                            </span>
                          </div>
                          <p className="text-xs text-muted-foreground mt-1" dir="ltr">
                            المسؤول: {entry.admin_uid}
                          </p>
                          {entry.reason && (
                            <p className="text-xs text-slate-600 mt-1">السبب: {entry.reason}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {app.status === 'submitted' && (
                  <div className="flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      className="bg-green-600 hover:bg-green-700"
                      disabled={busy}
                      onClick={() => handleApprove(app.id)}
                    >
                      {busy && decisionMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin ml-1" /> : <UserCheck className="w-4 h-4 ml-1" />}
                      الموافقة النهائية
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      disabled={busy}
                      onClick={() => { setRejectTarget(app.id); setRejectReason(""); }}
                    >
                      <UserX className="w-4 h-4 ml-1" /> رفض الطلب
                    </Button>
                  </div>
                )}

                {(app.status === 'approved' || app.status === 'admin_rejected') && (
                  <div className="flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy}
                      onClick={() => openRevise(app.id, app.status)}
                    >
                      {busy && reviseMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin ml-1" /> : <RotateCcw className="w-4 h-4 ml-1" />}
                      تعديل القرار
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
        {applications.length === 0 && (
          <div className="text-center py-12 text-muted-foreground">لا يوجد طلبات تمويل تنتظر القرار النهائي بعد.</div>
        )}
      </div>

      <Dialog open={rejectTarget != null} onOpenChange={(open) => !open && setRejectTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>سبب الرفض</DialogTitle>
            <DialogDescription>سيظهر هذا السبب للعميل ضمن حالة طلبه.</DialogDescription>
          </DialogHeader>
          <Textarea
            placeholder="مثال: عدم استقرار الدخل خلال الأشهر الأخيرة"
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            rows={4}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectTarget(null)}>إلغاء</Button>
            <Button variant="destructive" disabled={decisionMutation.isPending} onClick={handleReject}>
              {decisionMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : "تأكيد الرفض"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={reviseTarget != null} onOpenChange={(open) => !open && setReviseTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>تعديل القرار النهائي</DialogTitle>
            <DialogDescription>
              يُستخدم هذا لتصحيح قرار حديث اتُّخذ بالخطأ أو بناءً على معلومات غير محدّثة. سيتم إشعار العميل
              (والكفيل إن وُجد) بالتعديل، ولا يمكن تعديل قرار مرّت عليه أكثر من ١٤ يومًا.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <p className="text-sm font-medium mb-1">الحالة الجديدة</p>
              <Select value={reviseNewStatus} onValueChange={(value) => setReviseNewStatus(value as LoanApplicationReviseInputNewStatus)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="approved">الموافقة</SelectItem>
                  <SelectItem value="rejected">الرفض</SelectItem>
                  <SelectItem value="submitted">إعادة الطلب لبانتظار القرار النهائي</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <p className="text-sm font-medium mb-1">سبب التعديل</p>
              <Textarea
                placeholder="مثال: تمت الموافقة بالخطأ على طلب آخر، هذا القرار يصحّحه."
                value={reviseReason}
                onChange={(e) => setReviseReason(e.target.value)}
                rows={4}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setReviseTarget(null)}>إلغاء</Button>
            <Button disabled={reviseMutation.isPending} onClick={handleRevise}>
              {reviseMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : "تأكيد التعديل"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function formatGuarantorDecisionTimestamp(timestamp: string) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return timestamp;
  return new Intl.DateTimeFormat("ar-JO", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}
