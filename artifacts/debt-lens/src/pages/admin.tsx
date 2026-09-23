import { useState } from "react";
import { useListAdminUsers, useSubmitKycDecision, getListAdminUsersQueryKey } from "@workspace/api-client-react";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Loader2, UserCheck, UserX, AlertCircle } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

export default function AdminPage() {
  const queryClient = useQueryClient();
  const usersQuery = useListAdminUsers();
  const decisionMutation = useSubmitKycDecision();
  const [pendingUid, setPendingUid] = useState<string | null>(null);
  const { toast } = useToast();

  const handleDecision = async (uid: string, decision: "approved" | "rejected") => {
    setPendingUid(uid);
    try {
      await decisionMutation.mutateAsync({ data: { uid, decision } });
      queryClient.invalidateQueries({ queryKey: getListAdminUsersQueryKey() });
    } catch (error) {
      console.error("Error updating KYC decision", error);
      toast({
        variant: "destructive",
        title: "فشل حفظ القرار",
        description: "تعذر تحديث حالة المستخدم. يرجى المحاولة مرة أخرى.",
      });
    } finally {
      setPendingUid(null);
    }
  };

  if (usersQuery.isLoading) {
    return <div className="flex-1 flex items-center justify-center"><Loader2 className="w-8 h-8 animate-spin" /></div>;
  }

  if (usersQuery.isError || !usersQuery.data) {
    return (
      <div className="flex-1 flex items-center justify-center p-8 text-center text-destructive">
        <div>
          <AlertCircle className="w-12 h-12 mx-auto mb-4" />
          <p>حدث خطأ أثناء تحميل بيانات المستخدمين.</p>
        </div>
      </div>
    );
  }

  const { users, user_count } = usersQuery.data;

  return (
    <div className="flex-1 container mx-auto p-4 md:p-8">
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-2xl font-bold text-primary">لوحة الإدارة - قائمة العملاء</h1>
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
                      {user.review_status === 'approved' ? 'مقبول' :
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
                  <Button
                    size="sm"
                    variant="outline"
                    className="flex-1 bg-green-50 text-green-700 hover:bg-green-100 hover:text-green-800 border-green-200"
                    disabled={user.review_status === 'approved' || (decisionMutation.isPending && pendingUid === user.uid)}
                    onClick={() => handleDecision(user.uid, "approved")}
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
                    className="flex-1 bg-red-50 text-red-700 hover:bg-red-100 hover:text-red-800 border-red-200"
                    disabled={user.review_status === 'rejected' || (decisionMutation.isPending && pendingUid === user.uid)}
                    onClick={() => handleDecision(user.uid, "rejected")}
                  >
                    {decisionMutation.isPending && pendingUid === user.uid ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <><UserX className="w-4 h-4 ml-1" /> رفض</>
                    )}
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
    </div>
  );
}
