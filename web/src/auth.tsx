import { createContext, ReactNode, useContext } from "react";
import { User } from "@/api";

// Contexto leve pro usuário logado (mesmo espírito do LanguageContext em i18n.tsx) -- evita
// perfurar props em cada página só pra saber "sou eu o dono?" (DangerZone) ou "é a minha linha?"
// nas colunas de Dono das listagens.
const AuthContext = createContext<User | null>(null);

export function AuthProvider({ user, children }: { user: User; children: ReactNode }) {
  return <AuthContext.Provider value={user}>{children}</AuthContext.Provider>;
}

export function useCurrentUser(): User {
  const user = useContext(AuthContext);
  if (!user) throw new Error("useCurrentUser deve ser usado dentro de AuthProvider");
  return user;
}
