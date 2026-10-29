import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { api, User } from "./api";
import { AuthProvider } from "./auth";
import { LanguageProvider } from "./i18n";
import { Login } from "./pages/Login";
import { Layout } from "./pages/Layout";
import { Usuarios } from "./pages/Usuarios";
import { MinhaConta } from "./pages/MinhaConta";
import { Procedimentos } from "./features/executar-poc/pages/Procedimentos";
import { ProcedimentoUpload } from "./features/executar-poc/pages/ProcedimentoUpload";
import { ProcedimentoView } from "./features/executar-poc/pages/ProcedimentoView";
import { Pocs } from "./features/executar-poc/pages/Pocs";
import { PocUpload } from "./features/executar-poc/pages/PocUpload";
import { PocDetail } from "./features/executar-poc/pages/PocDetail";
import { PlanPoc } from "./features/planejar-poc/pages/PlanPoc";
import { Rfis } from "./features/rfi/pages/Rfis";
import { RfiUpload } from "./features/rfi/pages/RfiUpload";
import { RfiDetail } from "./features/rfi/pages/RfiDetail";

export function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setChecking(false));
  }, []);

  if (checking) return null;

  return (
    <LanguageProvider>
      {!user ? (
        <Login onLogin={setUser} />
      ) : (
        <AuthProvider user={user}>
          <Routes>
            <Route element={<Layout user={user} onLogout={() => setUser(null)} />}>
              <Route index element={<PlanPoc />} />
              <Route path="procedimentos" element={<Procedimentos />} />
              <Route path="procedimentos/novo" element={<ProcedimentoUpload />} />
              <Route path="procedimentos/:id" element={<ProcedimentoView />} />
              <Route path="pocs" element={<Pocs />} />
              <Route path="pocs/novo" element={<PocUpload />} />
              <Route path="pocs/:id" element={<PocDetail />} />
              <Route path="rfis" element={<Rfis />} />
              <Route path="rfis/novo" element={<RfiUpload />} />
              <Route path="rfis/:id" element={<RfiDetail />} />
              <Route path="usuarios" element={<Usuarios />} />
              <Route path="minha-conta" element={<MinhaConta user={user} onUserAtualizado={setUser} />} />
              <Route path="plan" element={<Navigate to="/" replace />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </AuthProvider>
      )}
    </LanguageProvider>
  );
}
