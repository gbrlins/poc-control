import { createContext, ReactNode, useContext, useEffect } from "react";
import { User } from "@/api";
import { registrarUsuario } from "@/features/planejar-poc/plannerStore";

// Contexto leve pro usuário logado (mesmo espírito do LanguageContext em i18n.tsx) -- evita
// perfurar props em cada página só pra saber "sou eu o dono?" (DangerZone) ou "é a minha linha?"
// nas colunas de Dono das listagens.
const AuthContext = createContext<User | null>(null);

export function AuthProvider({ user, children }: { user: User; children: ReactNode }) {
  // The embedded planner has no login of its own: it stamps each save with this name (see plannerStore).
  useEffect(() => registrarUsuario(user.email), [user.email]);
  return <AuthContext.Provider value={user}>{children}</AuthContext.Provider>;
}

export function useCurrentUser(): User {
  const user = useContext(AuthContext);
  if (!user) throw new Error("useCurrentUser deve ser usado dentro de AuthProvider");
  return user;
}
