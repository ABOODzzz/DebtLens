import { useState } from "react";
import { useLocation } from "wouter";
import { useAuth } from "@/lib/auth-context";
import { doc, updateDoc } from "firebase/firestore";
import { ref, uploadBytes } from "firebase/storage";
import { db, storage } from "@/lib/firebase";
import { useSubmitKyc } from "@workspace/api-client-react";
import { banks, allLenders } from "@/lib/lenders";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { FileUpload } from "@/components/ui/file-upload";
import { Loader2, Plus, Trash2, CheckCircle2, Building2, Briefcase, FileText, ShieldCheck } from "lucide-react";

const TOTAL_STEPS = 3;

export default function WizardPage() {
  const { user, profile } = useAuth();
  const [, setLocation] = useLocation();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);

  const submitKyc = useSubmitKyc();

  // Step 1: Identity verification (KYC) -- runs first so the AI check can
  // approve (or flag for manual review) before the person spends time
  // filling out the rest of their financial profile.
  const [legalName, setLegalName] = useState(profile?.fullName || "");
  const [nationalId, setNationalId] = useState("");
  const [idFront, setIdFront] = useState<File | null>(null);
  const [idBack, setIdBack] = useState<File | null>(null);
  const [selfie, setSelfie] = useState<File | null>(null);
  const [kycError, setKycError] = useState("");
  const [kycResult, setKycResult] = useState<{ reviewStatus: string; reviewReason: string | null } | null>(null);

  // Step 2: Bank account branch
  const [hasBankAccount, setHasBankAccount] = useState<boolean | null>(null);
  const [bankAccounts, setBankAccounts] = useState([{ bankName: "", accountNumber: "", isSalaryAccount: true }]);
  const [isRegisteredGuarantor, setIsRegisteredGuarantor] = useState<boolean | null>(null);

  const [monthlyIncome, setMonthlyIncome] = useState("");
  const [employerName, setEmployerName] = useState("");
  const [employmentType, setEmploymentType] = useState<"permanent" | "temporary" | "unemployed">("permanent");
  const [hasOwnBusiness, setHasOwnBusiness] = useState(false);

  // Step 3: Debts -- same list for both branches
  const [debts, setDebts] = useState<{ lenderName: string; startDate: string; remainingAmount: string }[]>([]);

  // Final submission status
  const [isSubmitted, setIsSubmitted] = useState(false);

  const handleAddBankAccount = () => {
    setBankAccounts([...bankAccounts, { bankName: "", accountNumber: "", isSalaryAccount: false }]);
  };

  const handleRemoveBankAccount = (index: number) => {
    setBankAccounts(bankAccounts.filter((_, i) => i !== index));
  };

  const handleAddDebt = () => {
    setDebts([...debts, { lenderName: "", startDate: "", remainingAmount: "" }]);
  };

  const handleRemoveDebt = (index: number) => {
    setDebts(debts.filter((_, i) => i !== index));
  };

  const validateStep1 = () => {
    return legalName !== "" && idFront !== null && idBack !== null && selfie !== null;
  };

  const validateStep2 = () => {
    if (hasBankAccount === null) return false;
    if (hasBankAccount) {
      return (
        bankAccounts.length > 0 &&
        bankAccounts.every((acc) => acc.bankName && acc.accountNumber) &&
        isRegisteredGuarantor !== null
      );
    } else {
      return monthlyIncome !== "" && Number(monthlyIncome) > 0;
    }
  };

  const validateStep3 = () => {
    // Debts are optional, but if added, fields must be filled
    if (debts.length === 0) return true;
    return debts.every((debt) => debt.lenderName && debt.startDate && debt.remainingAmount && Number(debt.remainingAmount) > 0);
  };

  const uploadFile = async (file: File, path: string): Promise<string> => {
    const storageRef = ref(storage, path);
    await uploadBytes(storageRef, file);
    return path; // API expects storage paths
  };

  const handleSubmitKyc = async () => {
    if (!user || !validateStep1()) return;
    setKycError("");
    setLoading(true);

    try {
      const idFrontPath = `kyc/${user.uid}/idFront_${Date.now()}.jpg`;
      const idBackPath = `kyc/${user.uid}/idBack_${Date.now()}.jpg`;
      const selfiePath = `kyc/${user.uid}/selfie_${Date.now()}.jpg`;

      await Promise.all([
        uploadFile(idFront!, idFrontPath),
        uploadFile(idBack!, idBackPath),
        uploadFile(selfie!, selfiePath),
      ]);

      await updateDoc(doc(db, "users", user.uid), {
        fullName: legalName,
        ...(nationalId ? { nationalId } : {}),
        kycPhotoPaths: { idFront: idFrontPath, idBack: idBackPath, selfie: selfiePath },
        updatedAt: new Date().toISOString(),
      });

      // The AI verdict (face match + document read) is computed server-side.
      // A strong match auto-approves the account right here -- no admin
      // round-trip needed. Anything less clear falls back to manual review,
      // but the person still continues filling out their financial profile.
      const res = await submitKyc.mutateAsync({
        data: {
          profile: { fullName: legalName, nationalId },
          photoPaths: [idFrontPath, idBackPath, selfiePath],
        },
      });

      setKycResult({ reviewStatus: res.reviewStatus, reviewReason: res.reason || null });
      setStep(2);
    } catch (error) {
      console.error("KYC submission failed", error);
      setKycError("تعذر إتمام التحقق من الهوية. يرجى المحاولة مرة أخرى.");
    } finally {
      setLoading(false);
    }
  };

  const handleFinalSubmit = async () => {
    if (!user) return;
    setLoading(true);

    try {
      const fullProfile = {
        hasBankAccount: hasBankAccount!,
        ...(hasBankAccount
          ? {
              bankAccounts,
              employerName,
              employmentType,
              isRegisteredGuarantor: isRegisteredGuarantor!,
            }
          : {
              monthlyIncome: Number(monthlyIncome),
              employerName,
              employmentType,
              hasOwnBusiness,
            }),
        debts: debts.map((d) => ({
          lenderName: d.lenderName,
          startDate: d.startDate,
          remainingAmount: Number(d.remainingAmount),
        })),
        profileCompleted: true,
        updatedAt: new Date().toISOString(),
      };

      await updateDoc(doc(db, "users", user.uid), fullProfile);
      setIsSubmitted(true);
    } catch (error) {
      console.error("Profile submission failed", error);
    } finally {
      setLoading(false);
    }
  };

  if (isSubmitted) {
    const reviewStatus = kycResult?.reviewStatus ?? "pending";
    const reviewReason = kycResult?.reviewReason;

    return (
      <div className="flex-1 container max-w-2xl mx-auto py-12 px-4">
        <Card className="glass-card text-center py-12">
          <CardContent className="space-y-6 flex flex-col items-center">
            {reviewStatus === "approved" ? (
              <div className="w-20 h-20 rounded-full bg-green-100 text-green-600 flex items-center justify-center">
                <CheckCircle2 className="w-10 h-10" />
              </div>
            ) : reviewStatus === "rejected" ? (
              <div className="w-20 h-20 rounded-full bg-destructive/10 text-destructive flex items-center justify-center">
                <Trash2 className="w-10 h-10" />
              </div>
            ) : (
              <div className="w-20 h-20 rounded-full bg-secondary/20 text-secondary flex items-center justify-center">
                <Loader2 className="w-10 h-10 animate-spin" />
              </div>
            )}

            <div className="space-y-2">
              <h2 className="text-2xl font-bold text-primary">
                {reviewStatus === "approved"
                  ? "تم قبول ملفك بنجاح!"
                  : reviewStatus === "rejected"
                    ? "نأسف، تم رفض طلبك"
                    : "جاري مراجعة ملفك"}
              </h2>
              <p className="text-muted-foreground max-w-md mx-auto">
                {reviewStatus === "approved"
                  ? "أهلاً بك في DebtLens. يمكنك الآن الاستفادة من جميع خدماتنا لتبسيط وإدارة ديونك."
                  : reviewStatus === "rejected"
                    ? reviewReason || "لم يستوف الملف الشروط المطلوبة."
                    : "يقوم فريقنا بمراجعة مستنداتك وتفاصيلك المالية. ستتلقى إشعاراً فور الانتهاء."}
              </p>
            </div>

            <Button onClick={() => setLocation("/dashboard")} size="lg" className="mt-4">
              الانتقال للوحة التحكم
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex-1 bg-muted/30 py-12 px-4">
      <div className="max-w-3xl mx-auto space-y-6">
        {/* Progress Bar */}
        <div className="flex items-center justify-between mb-8 relative">
          <div className="absolute left-0 right-0 top-1/2 -translate-y-1/2 h-1 bg-border z-0 rounded-full" />
          <div
            className="absolute right-0 top-1/2 -translate-y-1/2 h-1 bg-secondary z-0 rounded-full transition-all duration-500"
            style={{ width: `${((step - 1) / (TOTAL_STEPS - 1)) * 100}%` }}
          />

          {[1, 2, 3].map((num) => (
            <div
              key={num}
              className={`relative z-10 w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm transition-colors duration-300 ${
                step >= num ? "bg-secondary text-secondary-foreground shadow-md" : "bg-card border-2 border-border text-muted-foreground"
              }`}
            >
              {num < step ? <CheckCircle2 className="w-5 h-5" /> : num}
            </div>
          ))}
        </div>

        <Card className="glass-card border-none shadow-xl">
          <CardHeader className="bg-primary text-primary-foreground rounded-t-xl">
            <CardTitle className="text-xl">
              {step === 1 && "التحقق من الهوية (KYC)"}
              {step === 2 && "المعلومات المالية والبنكية"}
              {step === 3 && "سجل الديون والالتزامات"}
            </CardTitle>
            <CardDescription className="text-primary-foreground/80">
              {step === 1 && "خطوة أولى لتأمين حسابك والتحقق من هويتك عبر الذكاء الاصطناعي."}
              {step === 2 && "لنفهم مصادر دخلك وحساباتك البنكية."}
              {step === 3 && "قم بإضافة جميع قروضك والتزاماتك الحالية بدقة للحصول على أفضل خطة."}
            </CardDescription>
          </CardHeader>

          <CardContent className="p-8">
            {step === 1 && (
              <div className="space-y-8 animate-in fade-in slide-in-from-right-4">
                {kycError && (
                  <div className="p-3 text-sm bg-destructive/10 text-destructive border border-destructive/20 rounded-md">
                    {kycError}
                  </div>
                )}
                <div className="flex items-start gap-3 bg-primary/5 border border-primary/10 rounded-lg p-4">
                  <ShieldCheck className="w-5 h-5 text-primary flex-shrink-0 mt-0.5" />
                  <p className="text-sm text-muted-foreground">
                    يقوم نظام الذكاء الاصطناعي لدينا بمطابقة صورتك الشخصية مع بطاقة الهوية والتحقق من البيانات فوراً --
                    وقد تتم الموافقة على حسابك تلقائياً دون الحاجة لانتظار مراجعة يدوية.
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="space-y-2">
                    <Label htmlFor="legalName">الاسم القانوني الكامل</Label>
                    <Input
                      id="legalName"
                      value={legalName}
                      onChange={(e) => setLegalName(e.target.value)}
                      placeholder="كما هو في الهوية الشخصية"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="nationalId">الرقم الوطني (اختياري)</Label>
                    <Input
                      id="nationalId"
                      value={nationalId}
                      onChange={(e) => setNationalId(e.target.value)}
                      placeholder="10 أرقام"
                      className="dir-ltr text-left"
                    />
                  </div>
                </div>

                <div className="pt-4 border-t space-y-6">
                  <h4 className="font-semibold text-primary">المستندات المطلوبة</h4>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <FileUpload id="idFront" label="صورة الهوية (الوجه الأمامي)" onFileSelect={(f) => setIdFront(f)} />
                    <FileUpload id="idBack" label="صورة الهوية (الوجه الخلفي)" onFileSelect={(f) => setIdBack(f)} />
                    <FileUpload id="selfie" label="صورة شخصية (Selfie)" onFileSelect={(f) => setSelfie(f)} />
                  </div>
                </div>
              </div>
            )}

            {step === 2 && (
              <div className="space-y-8 animate-in fade-in slide-in-from-right-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div
                    onClick={() => setHasBankAccount(true)}
                    className={`p-4 border-2 rounded-xl cursor-pointer transition-all ${hasBankAccount === true ? "border-secondary bg-secondary/5 shadow-md" : "border-border hover:border-primary/30"}`}
                  >
                    <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center text-primary mb-3">
                      <Building2 className="w-5 h-5" />
                    </div>
                    <h3 className="font-bold text-primary">لدي حساب بنكي</h3>
                    <p className="text-xs text-muted-foreground mt-1">يتم تحويل راتبي أو دخلي إلى بنك معتمد</p>
                  </div>
                  <div
                    onClick={() => setHasBankAccount(false)}
                    className={`p-4 border-2 rounded-xl cursor-pointer transition-all ${hasBankAccount === false ? "border-secondary bg-secondary/5 shadow-md" : "border-border hover:border-primary/30"}`}
                  >
                    <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center text-primary mb-3">
                      <Briefcase className="w-5 h-5" />
                    </div>
                    <h3 className="font-bold text-primary">ليس لدي حساب بنكي</h3>
                    <p className="text-xs text-muted-foreground mt-1">أستلم راتبي نقداً أو عبر المحافظ الإلكترونية</p>
                  </div>
                </div>

                {hasBankAccount === true && (
                  <div className="space-y-6">
                    <h4 className="font-semibold border-b pb-2">تفاصيل الحسابات البنكية</h4>
                    {bankAccounts.map((acc, index) => (
                      <div key={index} className="p-4 bg-muted/30 rounded-lg border relative">
                        {index > 0 && (
                          <Button variant="ghost" size="icon" onClick={() => handleRemoveBankAccount(index)} className="absolute top-2 left-2 text-destructive hover:bg-destructive/10">
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        )}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                          <div className="space-y-2">
                            <Label>البنك</Label>
                            <Select
                              value={acc.bankName}
                              onValueChange={(val) => {
                                const newAccs = [...bankAccounts];
                                newAccs[index].bankName = val;
                                setBankAccounts(newAccs);
                              }}
                            >
                              <SelectTrigger>
                                <SelectValue placeholder="اختر البنك" />
                              </SelectTrigger>
                              <SelectContent>
                                {banks.map((bank) => (
                                  <SelectItem key={bank.ar} value={bank.ar}>{bank.ar}</SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                          <div className="space-y-2">
                            <Label>رقم الحساب / IBAN</Label>
                            <Input
                              value={acc.accountNumber}
                              onChange={(e) => {
                                const newAccs = [...bankAccounts];
                                newAccs[index].accountNumber = e.target.value;
                                setBankAccounts(newAccs);
                              }}
                              placeholder="مثال: JO12..."
                              className="dir-ltr text-left"
                            />
                          </div>
                        </div>
                        <label className="flex items-center gap-2 text-sm cursor-pointer">
                          <input
                            type="checkbox"
                            checked={acc.isSalaryAccount}
                            onChange={(e) => {
                              const newAccs = [...bankAccounts];
                              newAccs[index].isSalaryAccount = e.target.checked;
                              setBankAccounts(newAccs);
                            }}
                            className="rounded border-primary text-primary focus:ring-secondary"
                          />
                          هذا هو حساب الراتب الرئيسي
                        </label>
                      </div>
                    ))}
                    <Button type="button" variant="outline" onClick={handleAddBankAccount} className="w-full border-dashed border-2 gap-2 text-primary hover:text-primary">
                      <Plus className="w-4 h-4" /> إضافة حساب بنكي آخر
                    </Button>

                    <div className="pt-2 border-t space-y-4">
                      <h4 className="font-semibold border-b pb-2">جهة العمل</h4>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="space-y-2">
                          <Label>وين بتشتغل؟</Label>
                          <Input
                            value={employerName}
                            onChange={(e) => setEmployerName(e.target.value)}
                            placeholder="اسم الشركة أو المنشأة"
                          />
                        </div>
                        <div className="space-y-2">
                          <Label>نوع التوظيف</Label>
                          <Select value={employmentType} onValueChange={(val: any) => setEmploymentType(val)}>
                            <SelectTrigger>
                              <SelectValue placeholder="اختر النوع" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="permanent">عقد دائم</SelectItem>
                              <SelectItem value="temporary">عقد مؤقت / مياومة</SelectItem>
                              <SelectItem value="unemployed">غير موظف / عمل حر</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                      </div>
                    </div>

                    <div className="pt-2 border-t space-y-3">
                      <Label>هل أنت مسجل كضامن لأي جهة تمويل حالياً؟</Label>
                      <div className="grid grid-cols-2 gap-4">
                        <div
                          onClick={() => setIsRegisteredGuarantor(true)}
                          className={`p-3 text-center border-2 rounded-lg cursor-pointer transition-all ${isRegisteredGuarantor === true ? "border-secondary bg-secondary/5 shadow-md" : "border-border hover:border-primary/30"}`}
                        >
                          نعم
                        </div>
                        <div
                          onClick={() => setIsRegisteredGuarantor(false)}
                          className={`p-3 text-center border-2 rounded-lg cursor-pointer transition-all ${isRegisteredGuarantor === false ? "border-secondary bg-secondary/5 shadow-md" : "border-border hover:border-primary/30"}`}
                        >
                          لا
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {hasBankAccount === false && (
                  <div className="space-y-6">
                    <h4 className="font-semibold border-b pb-2">تفاصيل الدخل والعمل</h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label>الدخل الشهري (دينار أردني)</Label>
                        <Input
                          type="number"
                          value={monthlyIncome}
                          onChange={(e) => setMonthlyIncome(e.target.value)}
                          placeholder="مثال: 500"
                          min="0"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>نوع التوظيف</Label>
                        <Select value={employmentType} onValueChange={(val: any) => setEmploymentType(val)}>
                          <SelectTrigger>
                            <SelectValue placeholder="اختر النوع" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="permanent">عقد دائم</SelectItem>
                            <SelectItem value="temporary">عقد مؤقت / مياومة</SelectItem>
                            <SelectItem value="unemployed">غير موظف / عمل حر</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-2 md:col-span-2">
                        <Label>اسم جهة العمل (اختياري)</Label>
                        <Input
                          value={employerName}
                          onChange={(e) => setEmployerName(e.target.value)}
                          placeholder="اسم الشركة أو المنشأة"
                        />
                      </div>
                    </div>
                    <label className="flex items-center gap-2 text-sm cursor-pointer mt-2">
                      <input
                        type="checkbox"
                        checked={hasOwnBusiness}
                        onChange={(e) => setHasOwnBusiness(e.target.checked)}
                        className="rounded border-primary text-primary focus:ring-secondary"
                      />
                      لدي عملي التجاري الخاص (صاحب مصلحة)
                    </label>
                  </div>
                )}
              </div>
            )}

            {step === 3 && (
              <div className="space-y-6 animate-in fade-in slide-in-from-right-4">
                <div className="bg-primary/5 border border-primary/10 rounded-lg p-4 mb-6">
                  <div className="flex gap-3">
                    <FileText className="w-5 h-5 text-primary flex-shrink-0 mt-0.5" />
                    <div>
                      <h4 className="font-semibold text-primary">الشفافية هي مفتاح الحل</h4>
                      <p className="text-sm text-muted-foreground mt-1">يضمن إدراج جميع ديونك (القروض البنكية، تمويل الشركات، بطاقات الائتمان) حصولك على خطة توحيد دقيقة تناسب وضعك الفعلي.</p>
                    </div>
                  </div>
                </div>

                {debts.length === 0 ? (
                  <div className="text-center py-8 border-2 border-dashed rounded-xl border-border bg-muted/20">
                    <p className="text-muted-foreground mb-4">ليس لديك ديون مضافة بعد.</p>
                    <Button onClick={handleAddDebt} variant="outline" className="border-secondary text-primary hover:bg-secondary/10">
                      <Plus className="w-4 h-4 mr-2" /> إضافة دين / التزام
                    </Button>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {debts.map((debt, index) => (
                      <div key={index} className="p-4 bg-card border rounded-xl shadow-sm relative">
                        <Button variant="ghost" size="icon" onClick={() => handleRemoveDebt(index)} className="absolute top-2 left-2 text-destructive hover:bg-destructive/10">
                          <Trash2 className="w-4 h-4" />
                        </Button>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-2">
                          <div className="space-y-2">
                            <Label>الجهة المانحة</Label>
                            <Select
                              value={debt.lenderName}
                              onValueChange={(val) => {
                                const newDebts = [...debts];
                                newDebts[index].lenderName = val;
                                setDebts(newDebts);
                              }}
                            >
                              <SelectTrigger>
                                <SelectValue placeholder="اختر الجهة" />
                              </SelectTrigger>
                              <SelectContent>
                                {allLenders.map((lender) => (
                                  <SelectItem key={lender.ar} value={lender.ar}>{lender.ar}</SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                          <div className="space-y-2">
                            <Label>المبلغ المتبقي (دينار)</Label>
                            <Input
                              type="number"
                              value={debt.remainingAmount}
                              onChange={(e) => {
                                const newDebts = [...debts];
                                newDebts[index].remainingAmount = e.target.value;
                                setDebts(newDebts);
                              }}
                              placeholder="0.00"
                              min="0"
                            />
                          </div>
                          <div className="space-y-2">
                            <Label>تاريخ البداية (تقريبي)</Label>
                            <Input
                              type="month"
                              value={debt.startDate}
                              onChange={(e) => {
                                const newDebts = [...debts];
                                newDebts[index].startDate = e.target.value;
                                setDebts(newDebts);
                              }}
                              className="dir-ltr text-right"
                            />
                          </div>
                        </div>
                      </div>
                    ))}
                    <Button type="button" variant="outline" onClick={handleAddDebt} className="w-full border-dashed border-2 gap-2 text-primary hover:text-primary mt-4">
                      <Plus className="w-4 h-4" /> إضافة التزام آخر
                    </Button>
                  </div>
                )}
              </div>
            )}
          </CardContent>

          <CardFooter className="p-8 pt-0 flex justify-between bg-card rounded-b-xl border-t mt-4">
            <Button
              variant="outline"
              onClick={() => setStep(step - 1)}
              disabled={step === 1 || loading}
            >
              السابق
            </Button>

            {step === 1 && (
              <Button
                onClick={handleSubmitKyc}
                disabled={!validateStep1() || loading}
                className="bg-secondary text-secondary-foreground hover:bg-secondary/90 px-8 min-w-[120px]"
              >
                {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : "التالي"}
              </Button>
            )}

            {step === 2 && (
              <Button
                onClick={() => setStep(3)}
                disabled={!validateStep2()}
                className="bg-secondary text-secondary-foreground hover:bg-secondary/90 px-8"
              >
                التالي
              </Button>
            )}

            {step === 3 && (
              <Button
                onClick={handleFinalSubmit}
                disabled={!validateStep3() || loading}
                className="bg-primary text-primary-foreground hover:bg-primary/90 px-8 min-w-[120px]"
              >
                {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : "إرسال للمراجعة"}
              </Button>
            )}
          </CardFooter>
        </Card>
      </div>
    </div>
  );
}
