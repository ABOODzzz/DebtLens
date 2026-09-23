---
name: DebtLens manual-obligation analysis
description: Business rule for customers without bank statements and how their analysis and eligibility must be calculated.
---

Customers without verified statements must never be assessed from synthetic/demo transactions, whether or not they have a bank account. After they explicitly declare monthly obligations (including a valid zero-obligation declaration), comprehensive analysis, AI advice, dashboard totals, and financing eligibility use their self-reported monthly income minus those obligations until statements are available.

**Why:** invented transactions can materially distort credit eligibility. A bank-account holder's onboarding flow formerly omitted income altogether; a verified identity is not the same as a verified financial statement. The requirement is to calculate affordability from actual declared income and commitments when bank evidence does not exist, while labeling the figures as self-reported.

**How to apply:** preserve the distinction between “not declared yet” and “declared with total zero.” Eligibility calculations must use monthly normalized values, not sums across multiple statement months, and the server must continue enforcing the DTI ceiling independently of the model response.