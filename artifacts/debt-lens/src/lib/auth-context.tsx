import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { onAuthStateChanged, User } from 'firebase/auth';
import { doc, onSnapshot } from 'firebase/firestore';
import { auth, db, ADMIN_UID } from './firebase';
import { setAuthTokenGetter } from '@workspace/api-client-react';

export type ReviewStatus = 'pending' | 'approved' | 'rejected';

export interface UserProfile {
  fullName?: string;
  nationalId?: string;
  hasBankAccount?: boolean;
  bankAccounts?: { bankName: string; accountNumber: string; isSalaryAccount: boolean }[];
  monthlyIncome?: number;
  employerName?: string;
  employmentType?: 'permanent' | 'temporary' | 'unemployed';
  hasOwnBusiness?: boolean;
  isRegisteredGuarantor?: boolean;
  debts?: { lenderName: string; startDate: string; remainingAmount: number }[];
  kycPhotoPaths?: { idFront: string; idBack: string; selfie: string };
  profileCompleted?: boolean;
  reviewStatus?: ReviewStatus | null;
  reviewReason?: string | null;
  createdAt?: string;
  updatedAt?: string;
}

interface AuthContextType {
  user: User | null;
  profile: UserProfile | null;
  isAdmin: boolean;
  loading: boolean;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  profile: null,
  isAdmin: false,
  loading: true,
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    // Set up the API client auth getter ONCE
    setAuthTokenGetter(async () => {
      const currentUser = auth.currentUser;
      if (currentUser) {
        return await currentUser.getIdToken();
      }
      return null;
    });

    let unsubscribeProfile: () => void;

    const unsubscribeAuth = onAuthStateChanged(auth, (firebaseUser) => {
      setUser(firebaseUser);
      if (firebaseUser) {
        setIsAdmin(firebaseUser.uid === ADMIN_UID);
        
        // Listen to profile
        unsubscribeProfile = onSnapshot(doc(db, 'users', firebaseUser.uid), (docSnap) => {
          if (docSnap.exists()) {
            setProfile(docSnap.data() as UserProfile);
          } else {
            setProfile(null);
          }
          setLoading(false);
        }, (error) => {
          console.error("Error fetching profile:", error);
          setLoading(false);
        });
      } else {
        if (unsubscribeProfile) {
          unsubscribeProfile();
        }
        setProfile(null);
        setIsAdmin(false);
        setLoading(false);
      }
    });

    return () => {
      unsubscribeAuth();
      if (unsubscribeProfile) {
        unsubscribeProfile();
      }
    };
  }, []);

  return (
    <AuthContext.Provider value={{ user, profile, isAdmin, loading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
