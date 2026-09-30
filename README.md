# DebtLens

**An AI-powered personal debt management and loan eligibility platform for people in Jordan.**

## Live Demo

[Open DebtLens](https://debt-lens.replit.app)

## Overview

People can have loans and recurring expenses spread across different institutions, with no simple way to see their total monthly burden. A salary figure alone does not show how much is left after installments and other commitments, and a bank statement is difficult to interpret without a breakdown of its transactions.

DebtLens brings those figures together in a customer dashboard. It analyzes uploaded bank and financing statements, shows cash flow and debt obligations, and offers AI-assisted financial advice and a loan eligibility assessment. When a statement is unavailable, customers can declare their income and recurring obligations; the application distinguishes those self-reported figures from analyzed statement data.

The platform also provides restructuring scenarios and a consolidation-request flow. These are decision-support tools, **not automatic debt consolidation or guaranteed loan approval**. Administrators review identity documents, statements, guarantor relationships, and final application decisions.

## Key Features

- **Financial overview:** Monthly income, recurring obligations, outstanding debt, debt burden, and disposable income in the customer dashboard.
- **Statement analysis:** Admin-uploaded bank and financing statements are analyzed into transactions, monthly cash flow, transaction categories, and loan details. The customer can see the analysis of their bank statements.
- **AI-assisted guidance:** Anthropic Claude generates financial advice using available income, obligations, and analyzed statement context. The app does not treat every bank credit or transfer as recurring salary.
- **Eligibility assessment:** An AI-assisted recommendation and indicative credit score, with server-side debt-to-income limits checked independently of the model. The score is **not an official credit-bureau score**.
- **Restructuring and consolidation:** Proposed restructuring scenarios and a request flow for consolidating eligible debts; no automatic refinancing takes place.
- **Identity verification:** Registration and KYC submission with identity-document and selfie uploads, plus automated screening and admin review when required.
- **Digital guarantors:** Customers can request a guarantor; guarantors can respond, and final approval is subject to admin review and capacity checks.
- **Admin workspace:** Customer and statement review, financing-application decisions, guarantor decisions, and audit history.
- **Arabic-first interface:** Right-to-left Arabic UI with an English language option.

## Tech Stack

| Layer | Implementation |
| --- | --- |
| Frontend | React, TypeScript, Vite, Tailwind CSS, shadcn-style/Radix UI components, Recharts |
| Primary API | Python, FastAPI |
| Legacy API | TypeScript, Express (mounted separately at `/legacy-api`; the customer frontend uses FastAPI's `/api`) |
| AI | Anthropic Claude through Replit AI Integrations in the primary API; a Gemini integration is present in the legacy API |
| Identity and files | Firebase Authentication, Firestore, Firebase Storage |
| Additional persistence | PostgreSQL for loan applications and consolidation requests |
| Localization | Arabic RTL and English dictionaries |

## Architecture

```text
Customer / Admin browser
         |
         v
React + Vite (artifacts/debt-lens)
         |
         | /api via Vite proxy
         v
FastAPI (artifacts/debt-lens/server_py)
   |             |                 |
   |             |                 +--> Anthropic Claude (Replit AI Integrations)
   |             +--> PostgreSQL (applications / consolidation requests)
   +--> Firebase Auth, Firestore, Storage

Separate legacy service:
Express (artifacts/api-server) -- /legacy-api --> Firebase / PostgreSQL / Gemini
```

The frontend talks to FastAPI for the active financial, KYC, admin, and guarantor flows. The Express service remains in the workspace for legacy routes; it is not the primary API for the React app.

## How to Run Locally

1. Clone the repository and enter its root directory. Install **Node.js, pnpm, Python 3.11+, and uv** if they are not already available.
2. Install workspace dependencies with `pnpm install`, then install the root Python project dependencies with `uv sync`. The root `pyproject.toml` includes packages required for uploads and tests.
3. Configure the following environment variable **names** in your local environment or Replit Secrets. Do not commit credentials or a populated `.env` file:

   | Service | Environment variable names |
   | --- | --- |
   | Firebase web client | `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_PROJECT_ID`, `VITE_FIREBASE_STORAGE_BUCKET`, `VITE_FIREBASE_MESSAGING_SENDER_ID`, `VITE_FIREBASE_APP_ID` |
   | Firebase Admin SDK | `FIREBASE_SERVICE_ACCOUNT_JSON` |
   | Claude via Replit AI Integrations | `AI_INTEGRATIONS_ANTHROPIC_BASE_URL`, `AI_INTEGRATIONS_ANTHROPIC_API_KEY` |
   | PostgreSQL | `DATABASE_URL` |
   | Web process | `PORT`, `BASE_PATH` |

   `BASE_PATH` should be the URL path where the web app is mounted (the repository's web artifact uses the root path). The AI integration variables require access to the Replit AI Integrations proxy; without them, AI-assisted endpoints are unavailable. Authenticated routes also require a configured Firebase project. Database-backed application and consolidation flows require PostgreSQL.

4. Set `PORT` and `BASE_PATH`, then run the web artifact from the repository root:

   ```bash
   uv run bash artifacts/debt-lens/dev.sh
   ```

   The script starts FastAPI on an internal port and Vite on `PORT`; Vite proxies `/api` to FastAPI. On Replit, the artifact's **web** workflow already provides the web process settings and runs `bash dev.sh`.

5. **Optional legacy API:** In a separate process with its own `PORT`, run `pnpm --filter @workspace/api-server run dev`. This Express server uses `/legacy-api` and is not needed to serve the main React/FastAPI experience. Some legacy endpoints also require the Gemini integration (`AI_INTEGRATIONS_GEMINI_BASE_URL`, `AI_INTEGRATIONS_GEMINI_API_KEY`).

To run the Python contract tests, use `uv run python -m pytest artifacts/debt-lens/server_py/tests/`. The React app can be type-checked with `pnpm --filter @workspace/debt-lens run typecheck`.

## Screenshots (add images here)

Add screenshots of the customer dashboard, statement analysis, eligibility result, and admin review here.

## Disclaimer

DebtLens is a portfolio/demo project built with Replit Agent. Its analyses, AI-generated suggestions, and indicative scores are not professional financial advice, an official credit report, or a promise of financing. Financial and identity decisions require appropriate human review.