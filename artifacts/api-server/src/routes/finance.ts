import { Router, type IRouter } from "express";
import {
  GetFinancialSummaryResponse,
  AnalyzeFinancesBody,
  AnalyzeFinancesResponse,
  GetRestructurePlanResponse,
  GetAdviceResponse,
  RequestConsolidationResponse,
  AssessLoanEligibilityResponse,
} from "@workspace/api-zod";
import { db, consolidationRequestsTable } from "@workspace/db";
import { verifyFirebaseAuth } from "../middlewares/firebaseAuth";
import { requireCompletedProfile, ProfileNotFoundError } from "../lib/userProfile";
import { computeFinancials } from "../lib/financials";
import { ai } from "@workspace/integrations-gemini-ai";

const router: IRouter = Router();

router.use(verifyFirebaseAuth);

router.get("/financial-summary", async (req, res) => {
  try {
    const profile = await requireCompletedProfile(req.uid!);
    const computed = computeFinancials(profile);
    const data = GetFinancialSummaryResponse.parse({
      totalMonthlyIncome: computed.monthlyIncome,
      totalMonthlyDebtPayments: computed.estimatedMonthlyDebtPayments,
      totalRemainingDebt: computed.totalRemainingDebt,
      activeLoansCount: computed.activeLoansCount,
      financingInstitutionsCount: computed.financingInstitutionsCount,
      debtToIncomeRatio: computed.debtToIncomeRatio,
      hasActiveLoans: computed.hasActiveLoans,
      hasMultipleFinancingInstitutions: computed.hasMultipleFinancingInstitutions,
    });
    res.json(data);
  } catch (err) {
    if (err instanceof ProfileNotFoundError) {
      res.status(404).json({ error: "Profile not found" });
      return;
    }
    req.log.error({ err }, "Failed to compute financial summary");
    res.status(503).json({ error: "Finance service unavailable" });
  }
});

router.post("/analyze", async (req, res) => {
  const parsed = AnalyzeFinancesBody.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: "Invalid analyze request" });
    return;
  }

  try {
    const profile = await requireCompletedProfile(req.uid!);
    const computed = computeFinancials(profile);
    const debtBreakdown = computed.debts.map((d) => ({
      lenderName: d.lenderName,
      remainingAmount: d.remainingAmount,
      startDate: d.startDate,
      estimatedMonthlyBurden: d.remainingAmount / 24,
    }));

    const insights: string[] = [];
    if (debtBreakdown.length > 0) {
      const largest = [...debtBreakdown].sort(
        (a, b) => b.remainingAmount - a.remainingAmount,
      )[0]!;
      insights.push(
        `أكبر التزام مالي حاليًا هو لدى ${largest.lenderName} بمبلغ متبقٍ قدره ${largest.remainingAmount.toFixed(0)} دينار.`,
      );
    }
    insights.push(
      computed.debtToIncomeRatio > 0.45
        ? "نسبة الالتزامات إلى الدخل مرتفعة، يُنصح بخطة إعادة هيكلة."
        : "نسبة الالتزامات إلى الدخل ضمن الحدود المقبولة حاليًا.",
    );
    if (computed.hasMultipleFinancingInstitutions) {
      insights.push(
        "يمكن التفكير في دمج القروض لدى جهات تمويل متعددة لتبسيط السداد.",
      );
    }

    const summary =
      parsed.data.type === "transactions"
        ? `تحليل الالتزامات: ${computed.activeLoansCount} التزام نشط بإجمالي ${computed.totalRemainingDebt.toFixed(0)} دينار متبقٍ.`
        : `تحليل شامل: دخل شهري ${computed.monthlyIncome.toFixed(0)} دينار مقابل عبء شهري تقديري ${computed.estimatedMonthlyDebtPayments.toFixed(0)} دينار.`;

    const data = AnalyzeFinancesResponse.parse({
      type: parsed.data.type,
      summary,
      debtBreakdown,
      totalRemainingDebt: computed.totalRemainingDebt,
      debtToIncomeRatio: computed.debtToIncomeRatio,
      insights,
    });
    res.json(data);
  } catch (err) {
    if (err instanceof ProfileNotFoundError) {
      res.status(404).json({ error: "Profile not found" });
      return;
    }
    req.log.error({ err }, "Failed to analyze finances");
    res.status(503).json({ error: "Finance service unavailable" });
  }
});

router.post("/restructure", async (req, res) => {
  try {
    const profile = await requireCompletedProfile(req.uid!);
    const computed = computeFinancials(profile);

    if (!computed.hasActiveLoans) {
      res.status(422).json({ error: "No active loans to restructure" });
      return;
    }

    const targetRatio = Math.min(computed.debtToIncomeRatio, 0.35);
    const targetMonthlyBurden = computed.monthlyIncome * targetRatio;
    const months =
      targetMonthlyBurden > 0
        ? Math.ceil(computed.totalRemainingDebt / targetMonthlyBurden)
        : 36;

    const sorted = [...computed.debts].sort(
      (a, b) => b.remainingAmount - a.remainingAmount,
    );
    const steps = sorted.map((d, idx) => ({
      lenderName: d.lenderName,
      action: idx === 0 ? "إعادة جدولة" : "توحيد الدفعات",
      detail: `تمديد فترة السداد لمبلغ ${d.remainingAmount.toFixed(0)} دينار على مدى ${months} شهرًا تقريبًا لتقليل العبء الشهري.`,
    }));

    const data = GetRestructurePlanResponse.parse({
      currentMonthlyBurden: computed.estimatedMonthlyDebtPayments,
      targetMonthlyBurden,
      currentDebtToIncomeRatio: computed.debtToIncomeRatio,
      targetDebtToIncomeRatio: targetRatio,
      months,
      steps,
    });
    res.json(data);
  } catch (err) {
    if (err instanceof ProfileNotFoundError) {
      res.status(404).json({ error: "Profile not found" });
      return;
    }
    req.log.error({ err }, "Failed to build restructure plan");
    res.status(503).json({ error: "Finance service unavailable" });
  }
});

router.post("/advice", async (req, res) => {
  try {
    const profile = await requireCompletedProfile(req.uid!);
    const computed = computeFinancials(profile);

    const prompt = `أنت مستشار مالي أردني. بناءً على البيانات التالية لعميل (بدون ذكر أي معلومات تعريفية):
- الدخل الشهري: ${computed.monthlyIncome.toFixed(0)} دينار أردني
- عدد الالتزامات النشطة: ${computed.activeLoansCount}
- إجمالي الدين المتبقي: ${computed.totalRemainingDebt.toFixed(0)} دينار أردني
- نسبة الدين إلى الدخل التقديرية: ${(computed.debtToIncomeRatio * 100).toFixed(0)}%

اكتب نصيحة مالية عملية ومختصرة (3-5 جمل) باللغة العربية الفصحى المبسطة تساعد هذا العميل على إدارة التزاماته المالية بشكل أفضل.`;

    const response = await ai.models.generateContent({
      model: "gemini-2.5-flash",
      contents: prompt,
    });

    const advice = response.text?.trim();
    if (!advice) {
      throw new Error("Empty response from Gemini");
    }

    const data = GetAdviceResponse.parse({
      advice,
      generatedAt: new Date().toISOString(),
    });
    res.json(data);
  } catch (err) {
    if (err instanceof ProfileNotFoundError) {
      res.status(404).json({ error: "Profile not found" });
      return;
    }
    req.log.error({ err }, "Failed to generate AI advice");
    res.status(503).json({ error: "AI service unavailable" });
  }
});

router.post("/consolidation-request", async (req, res) => {
  try {
    const profile = await requireCompletedProfile(req.uid!);
    const computed = computeFinancials(profile);

    if (!computed.hasMultipleFinancingInstitutions) {
      res
        .status(422)
        .json({ error: "Fewer than 2 financing institutions on file" });
      return;
    }

    const CONSOLIDATED_TERM_MONTHS = 36;
    const estimatedConsolidatedMonthlyPayment =
      computed.totalRemainingDebt / CONSOLIDATED_TERM_MONTHS;

    const [inserted] = await db
      .insert(consolidationRequestsTable)
      .values({
        uid: req.uid!,
        status: "submitted",
        institutionsIncluded: computed.financingInstitutionsCount,
        estimatedConsolidatedMonthlyPayment: estimatedConsolidatedMonthlyPayment.toFixed(2),
      })
      .returning();

    const data = RequestConsolidationResponse.parse({
      id: inserted!.id,
      status: "submitted",
      estimatedConsolidatedMonthlyPayment,
      institutionsIncluded: computed.financingInstitutionsCount,
      createdAt: inserted!.createdAt.toISOString(),
    });
    res.status(201).json(data);
  } catch (err) {
    if (err instanceof ProfileNotFoundError) {
      res.status(404).json({ error: "Profile not found" });
      return;
    }
    req.log.error({ err }, "Failed to record consolidation request");
    res.status(503).json({ error: "Finance service unavailable" });
  }
});

router.post("/ai-loan-assessment", async (req, res) => {
  try {
    const profile = await requireCompletedProfile(req.uid!);
    const computed = computeFinancials(profile);

    const prompt = `أنت محلل ائتماني. بناءً على البيانات التالية لعميل (بدون أي معلومات تعريفية):
- الدخل الشهري: ${computed.monthlyIncome.toFixed(0)} دينار أردني
- عدد الالتزامات النشطة: ${computed.activeLoansCount}
- إجمالي الدين المتبقي: ${computed.totalRemainingDebt.toFixed(0)} دينار أردني
- نسبة الدين إلى الدخل التقديرية: ${(computed.debtToIncomeRatio * 100).toFixed(0)}%

قيّم أهلية هذا العميل للحصول على تمويل إضافي. أعد الإجابة بصيغة JSON فقط بدون أي نص إضافي وبالمخطط التالي:
{"eligible": boolean, "eligibilityScore": integer من 0 إلى 100, "maxRecommendedAmount": رقم بالدينار الأردني, "reasoning": "شرح موجز بالعربية"}`;

    const response = await ai.models.generateContent({
      model: "gemini-2.5-flash",
      contents: prompt,
      config: { responseMimeType: "application/json" },
    });

    const raw = response.text?.trim();
    if (!raw) {
      throw new Error("Empty response from Gemini");
    }

    const parsed = JSON.parse(raw);
    const data = AssessLoanEligibilityResponse.parse({
      eligible: Boolean(parsed.eligible),
      eligibilityScore: Math.max(0, Math.min(100, Math.round(parsed.eligibilityScore))),
      maxRecommendedAmount: Number(parsed.maxRecommendedAmount) || 0,
      reasoning: String(parsed.reasoning ?? ""),
    });
    res.json(data);
  } catch (err) {
    if (err instanceof ProfileNotFoundError) {
      res.status(404).json({ error: "Profile not found" });
      return;
    }
    req.log.error({ err }, "Failed AI loan assessment");
    res.status(503).json({ error: "AI service unavailable" });
  }
});

export default router;
