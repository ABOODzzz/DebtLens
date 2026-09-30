Create a professional README.md file in the project root for my GitHub repository. Write it in clear English (the app UI is in Arabic, but the README must be English).

Before writing, read through the actual codebase (artifacts/debt-lens and artifacts/api-server) so every claim is accurate — do not invent features.

Structure it like this:

1. **Title + one-line description** — DebtLens: an AI-powered personal debt management and loan eligibility platform (fintech).

2. **Live Demo** — https://debt-lens.replit.app

3. **Overview** — 2-3 paragraphs: the problem it solves (people struggle with scattered debts, unclear obligations, and not knowing their loan eligibility), and how DebtLens helps users analyze their financial situation, consolidate obligations, and check loan eligibility.

4. **Key Features** — a bulleted list based on what the code actually implements. Include things like: monthly budget/expense analysis, debt consolidation view, AI-powered financial analysis (Claude), loan eligibility scoring, KYC flow, guarantor network/model, admin dashboard, Arabic RTL UI. Verify each against the code before including it.

5. **Tech Stack** — a table or list: Frontend (React, Vite, Tailwind, shadcn — verify), Backend API (Python FastAPI + TypeScript/Express — verify what's actually used), AI (Anthropic Claude via Replit AI integrations), Auth & Database (Firebase), i18n (Arabic RTL).

6. **Architecture** — a short explanation with a simple diagram (ASCII or mermaid) of how the frontend, Python backend, TypeScript API server, and Firebase connect.

7. **How to Run Locally** — clear steps: clone, install dependencies, required environment variables (list them exactly as names only, e.g. VITE_FIREBASE_API_KEY, AI_INTEGRATIONS_ANTHROPIC_API_KEY — NEVER include real values), and how to start each service.

8. **Screenshots** — leave a placeholder section like "## Screenshots (add images here)".

9. **Disclaimer** — a short note that this is a portfolio/demo project built with Replit Agent, not production financial advice.

Important: Do NOT include any API keys, secrets, or .env values anywhere in the README. After creating the file, commit and push it to GitHub (origin main).