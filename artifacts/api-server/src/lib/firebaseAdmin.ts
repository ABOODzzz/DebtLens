import { cert, getApps, initializeApp, type App } from "firebase-admin/app";
import { getAuth } from "firebase-admin/auth";
import { getFirestore } from "firebase-admin/firestore";
import { logger } from "./logger";

const rawServiceAccount = process.env.FIREBASE_SERVICE_ACCOUNT_JSON;

if (!rawServiceAccount) {
  throw new Error(
    "FIREBASE_SERVICE_ACCOUNT_JSON must be set. Add the Firebase Admin SDK service account JSON.",
  );
}

let serviceAccount: Record<string, unknown>;
try {
  serviceAccount = JSON.parse(rawServiceAccount);
} catch (err) {
  logger.error({ err }, "Failed to parse FIREBASE_SERVICE_ACCOUNT_JSON as JSON");
  throw new Error("FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON");
}

let app: App;
if (getApps().length === 0) {
  app = initializeApp({
    credential: cert(serviceAccount as never),
  });
} else {
  app = getApps()[0]!;
}

export const adminAuth = getAuth(app);
export const adminDb = getFirestore(app);

/** Fixed UID of the single admin account; used for admin-gated logic. */
export const ADMIN_UID = "f293DyBAsCMK3Tws4no3metSvhB3";
