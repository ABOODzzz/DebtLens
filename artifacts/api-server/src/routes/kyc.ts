import { Router, type IRouter } from "express";
import { FieldValue } from "firebase-admin/firestore";
import { SubmitKycBody, SubmitKycResponse } from "@workspace/api-zod";
import { verifyFirebaseAuth } from "../middlewares/firebaseAuth";
import { adminDb } from "../lib/firebaseAdmin";
import { computeFinancials, type UserProfile } from "../lib/financials";

const router: IRouter = Router();

type ReviewStatus = "approved" | "pending" | "rejected";

function decideReview(profile: UserProfile): {
  reviewStatus: ReviewStatus;
  reason: string | null;
} {
  const { monthlyIncome, debtToIncomeRatio } = computeFinancials(profile);

  if (monthlyIncome <= 0) {
    return {
      reviewStatus: "rejected",
      reason: "لم يتم تحديد دخل شهري صالح لهذا الحساب.",
    };
  }

  if (profile.employmentType === "unemployed" && !profile.hasOwnBusiness) {
    return {
      reviewStatus: "pending",
      reason: "الحالة الوظيفية تتطلب مراجعة يدوية إضافية.",
    };
  }

  if (!profile.nationalId) {
    return {
      reviewStatus: "pending",
      reason: "بانتظار التحقق اليدوي من الهوية الوطنية.",
    };
  }

  if (debtToIncomeRatio > 0.75) {
    return {
      reviewStatus: "rejected",
      reason: "نسبة الالتزامات الشهرية إلى الدخل مرتفعة جدًا.",
    };
  }

  if (debtToIncomeRatio > 0.45) {
    return {
      reviewStatus: "pending",
      reason: "نسبة الالتزامات إلى الدخل تتطلب مراجعة يدوية.",
    };
  }

  return { reviewStatus: "approved", reason: null };
}

router.post("/kyc/submit", verifyFirebaseAuth, async (req, res) => {
  const parsed = SubmitKycBody.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: "Invalid KYC submission" });
    return;
  }

  const { profile, photoPaths } = parsed.data;
  const uid = req.uid!;

  const decision = decideReview(profile as UserProfile);

  try {
    const docRef = adminDb.collection("users").doc(uid);
    const existing = await docRef.get();

    await docRef.set(
      {
        ...profile,
        kycPhotoPaths: {
          idFront: photoPaths[0],
          idBack: photoPaths[1],
          selfie: photoPaths[2],
        },
        profileCompleted: true,
        reviewStatus: decision.reviewStatus,
        reviewReason: decision.reason,
        updatedAt: FieldValue.serverTimestamp(),
        ...(existing.exists ? {} : { createdAt: FieldValue.serverTimestamp() }),
      },
      { merge: true },
    );
  } catch (err) {
    req.log.error({ err }, "Failed to persist KYC submission");
    res.status(503).json({ error: "Review service unavailable" });
    return;
  }

  const data = SubmitKycResponse.parse({
    reviewStatus: decision.reviewStatus,
    reason: decision.reason,
  });
  res.json(data);
});

export default router;
