import { adminDb } from "./firebaseAdmin";
import type { UserProfile } from "./financials";

export class ProfileNotFoundError extends Error {
  constructor() {
    super("Profile not found or incomplete");
    this.name = "ProfileNotFoundError";
  }
}

export async function requireCompletedProfile(
  uid: string,
): Promise<UserProfile> {
  const snap = await adminDb.collection("users").doc(uid).get();
  if (!snap.exists) {
    throw new ProfileNotFoundError();
  }
  const data = snap.data() as UserProfile;
  if (!data.profileCompleted) {
    throw new ProfileNotFoundError();
  }
  return data;
}
