import type { NextFunction, Request, Response } from "express";
import { adminAuth } from "../lib/firebaseAdmin";

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace Express {
    interface Request {
      uid?: string;
    }
  }
}

export async function verifyFirebaseAuth(
  req: Request,
  res: Response,
  next: NextFunction,
): Promise<void> {
  const header = req.headers.authorization;
  if (!header || !header.startsWith("Bearer ")) {
    res.status(401).json({ error: "Missing bearer token" });
    return;
  }

  const idToken = header.slice("Bearer ".length);

  try {
    const decoded = await adminAuth.verifyIdToken(idToken);
    req.uid = decoded.uid;
    next();
  } catch (err) {
    req.log.warn({ err }, "Failed to verify Firebase ID token");
    res.status(401).json({ error: "Invalid or expired token" });
  }
}
