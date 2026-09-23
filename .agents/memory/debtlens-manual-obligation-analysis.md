---
name: DebtLens manual-obligation analysis
description: Business rule for customers without bank statements and how their analysis and eligibility must be calculated.
---

Customers without verified statements must never be assessed from synthetic/demo transactions, whether or not they have a bank account. After they explicitly declare monthly obligations (including a valid zero-obligation declaration), comprehensive analysis, AI advice, dashboard totals, and financing eligibility use their self-reported monthly income minus those obligations until statements are available.

**Why:** invented transactions can materially distort credit eligibility. A bank-account holder's onboarding flow formerly omitted income altogether; a verified identity is not the same as a verified financial statement. The requirement is to calculate affordability from actual declared income and commitments when bank evidence does not exist, while labeling the figures as self-reported.

**How to apply:** preserve the distinction between “not declared yet” and “declared with total zero.” Eligibility calculations must use monthly normalized values, not sums across multiple statement months, and the server must continue enforcing the DTI ceiling independently of the model response.

For analyzed bank statements, display the actual credit/debit cash flow and transaction categories separately from recurring monthly income. Only explicitly categorized salary credits, averaged over salary months, can replace the declared salary; transfers or other credits must not become recurring income. Feed that same statement cash flow into advice and eligibility context without silently classifying all bank debits as recurring obligations.

**Why:** statement summaries include transfers and one-off movements that can dwarf salary, so treating total credits as salary (or every debit as a loan payment) would make affordability decisions unsafe.

**How to apply:** keep statement cash flow visible to customers and admins, label any fallback salary as self-reported, and base deterministic loan ceilings on normalized monthly income plus known recurring obligations.