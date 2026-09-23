import {
  boolean,
  integer,
  numeric,
  pgTable,
  serial,
  text,
  timestamp,
} from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

// A customer's end-to-end loan/financing application: the requested amount
// and purpose, a snapshot of the AI eligibility assessment taken at
// submission time, and a status that walks through the connected journey
// from application -> (optional) digital guarantor -> admin review.
//
// `guarantorRelationshipId` links to a Firestore `guarantorRelationships`
// document (see server_py/guarantor.py) when `requiresGuarantor` is true --
// stored as text since Firestore doc ids aren't integers. It is set once the
// applicant requests a guarantor for this specific application, and the
// admin's final guarantor decision (server_py/admin_routes.py) flips this
// row's status back to `submitted` (approved) or `awaiting_guarantor`
// (rejected, so the applicant can try a different guarantor).
//
// Once a row reaches `submitted`, it awaits a *separate* final disbursement
// decision from an admin (see admin_routes.py's loan_application_decision),
// which moves it to the terminal `approved` or `admin_rejected` state and
// records the reason (for a rejection) in `adminDecisionReason`.
export const loanApplicationsTable = pgTable("loan_applications", {
  id: serial("id").primaryKey(),
  uid: text("uid").notNull(),
  requestedAmount: numeric("requested_amount", {
    precision: 12,
    scale: 2,
  }).notNull(),
  purpose: text("purpose").notNull(),
  // ineligible | awaiting_guarantor | submitted | approved | admin_rejected | rejected
  status: text("status").notNull().default("submitted"),
  requiresGuarantor: boolean("requires_guarantor").notNull().default(false),
  guarantorRelationshipId: text("guarantor_relationship_id"),
  adminDecisionReason: text("admin_decision_reason"),
  eligible: boolean("eligible").notNull(),
  riskTier: text("risk_tier"),
  creditScore: integer("credit_score"),
  recommendedAmount: numeric("recommended_amount", {
    precision: 12,
    scale: 2,
  }),
  interestRate: numeric("interest_rate", { precision: 5, scale: 2 }),
  termMonths: integer("term_months"),
  monthlyInstallment: numeric("monthly_installment", {
    precision: 12,
    scale: 2,
  }),
  totalRepayment: numeric("total_repayment", { precision: 12, scale: 2 }),
  recommendation: text("recommendation").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
});

export const insertLoanApplicationSchema = createInsertSchema(
  loanApplicationsTable,
).omit({ id: true, createdAt: true, updatedAt: true });
export type InsertLoanApplication = z.infer<
  typeof insertLoanApplicationSchema
>;
export type LoanApplication = typeof loanApplicationsTable.$inferSelect;
