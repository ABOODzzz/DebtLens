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
} from "@workspace/api-client-react";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Loader2, UserCheck, UserX, AlertCircle, Eye, ShieldCheck, Sparkles, ImageOff } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

export default function AdminPage() {
  return (
    <div className="flex-1 container mx-auto p-4 md:p-8">
      <h1 className="text-2xl font-bold text-primary mb-6">لوحة الإدارة</h1>
      <Tabs defaultValue="users" className="w-full">
        <TabsList className="mb-6">
          <TabsTrigger value="users">العملاء</TabsTrigger>
          <TabsTrigger value="guarantors">طلبات الكفيل الرقمي</TabsTrigger>
        </TabsList>
        <TabsContent value="users">
          <UsersTab />
        </TabsContent>
        <TabsContent value="guarantors">
          <GuarantorRequestsTab />
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

function GuarantorRequestsTab() {
  const queryClient = useQueryClient();
  const requestsQuery = useListGuarantorRequests();
  const insightMutation = useGetGuarantorInsight();
  const decisionMutation = useSubmitGuarantorDecision();
  const [insightByRequester, setInsightByRequester] = useState<Record<string, any>>({});
  const [activeRequester, setActiveRequester] = useState<string | null>(null);
  const { toast } = useToast();

  const invalidate = () => queryClient.invalidateQueries({ queryKey: getListGuarantorRequestsQueryKey() });

  const handleGetInsight = async (requesterUid: string) => {
    setActiveRequester(requesterUid);
    try {
      const result = await insightMutation.mutateAsync({ data: { requester_uid: requesterUid } });
      setInsightByRequester((prev) => ({ ...prev, [requesterUid]: result }));
    } catch (error) {
      toast({ variant: "destructive", title: "تعذر توليد التحليل", description: "يرجى المحاولة مرة أخرى." });
    } finally {
      setActiveRequester(null);
    }
  };

  const handleDecision = async (requesterUid: string, decision: "approved" | "rejected") => {
    setActiveRequester(requesterUid);
    try {
      await decisionMutation.mutateAsync({ data: { requester_uid: requesterUid, decision } });
      invalidate();
    } catch (error) {
      toast({ variant: "destructive", title: "تعذر حفظ القرار", description: "يرجى المحاولة مرة أخرى." });
    } finally {
      setActiveRequester(null);
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
          const insight = insightByRequester[req.requester_uid];
          const busy = activeRequester === req.requester_uid && (insightMutation.isPending || decisionMutation.isPending);
          return (
            <Card key={req.requester_uid}>
              <CardContent className="p-4 space-y-4">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-2">
                    <ShieldCheck className="w-5 h-5 text-secondary" />
                    <span className="font-bold">{req.requester_name}</span>
                    <span className="text-muted-foreground text-sm">يطلب كفالة من</span>
                    <span className="font-bold">{req.guarantor_name || "-"}</span>
                  </div>
                  <Badge variant={req.status === 'approved' ? 'default' : req.status === 'rejected' ? 'destructive' : 'secondary'}>
                    {req.status === 'awaiting_admin_review' ? 'بانتظار قرار الإدارة' : req.status === 'approved' ? 'موافق عليه' : 'مرفوض'}
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
                    <Button size="sm" variant="outline" disabled={busy} onClick={() => handleGetInsight(req.requester_uid)}>
                      {busy && insightMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin ml-1" /> : <Sparkles className="w-4 h-4 ml-1" />}
                      تحليل بالذكاء الاصطناعي
                    </Button>
                    <Button
                      size="sm"
                      className="bg-green-600 hover:bg-green-700"
                      disabled={busy}
                      onClick={() => handleDecision(req.requester_uid, "approved")}
                    >
                      {busy && decisionMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin ml-1" /> : <UserCheck className="w-4 h-4 ml-1" />}
                      الموافقة على الكفالة
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      disabled={busy}
                      onClick={() => handleDecision(req.requester_uid, "rejected")}
                    >
                      {busy && decisionMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin ml-1" /> : <UserX className="w-4 h-4 ml-1" />}
                      رفض الكفالة
                    </Button>
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
    </div>
  );
}
