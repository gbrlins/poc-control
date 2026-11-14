import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useParams } from "react-router-dom";
import { api, User } from "./api";
import { AuthProvider } from "./auth";
import { LanguageProvider } from "./i18n";
import { Login } from "./pages/Login";
import { Layout } from "./pages/Layout";
import { Home } from "./pages/Home";
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
import { Licitacoes } from "./features/licitacoes/pages/Licitacoes";

function LegacyProcedimentoRedirect() {
  const { id } = useParams<{ id: string }>();
  return <Navigate to={`/procedures/${id}`} replace />;
}

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
              <Route index element={<Home />} />
              <Route path="plan" element={<PlanPoc />} />
              <Route path="procedures" element={<Procedimentos />} />
              <Route path="procedures/new" element={<ProcedimentoUpload />} />
              <Route path="procedures/:id" element={<ProcedimentoView />} />
              <Route path="pocs" element={<Pocs />} />
              <Route path="pocs/new" element={<PocUpload />} />
              <Route path="pocs/:id" element={<PocDetail />} />
              <Route path="rfis" element={<Rfis />} />
              <Route path="rfis/new" element={<RfiUpload />} />
              <Route path="rfis/:id" element={<RfiDetail />} />
              <Route path="tenders" element={<Licitacoes />} />
              <Route path="users" element={<Usuarios />} />
              <Route path="my-account" element={<MinhaConta user={user} onUserAtualizado={setUser} />} />
              {/* Legacy pt-BR paths redirect to their English equivalents (v2 rename, item 2.2). */}
              <Route path="planejar" element={<Navigate to="/plan" replace />} />
              <Route path="procedimentos" element={<Navigate to="/procedures" replace />} />
              <Route path="procedimentos/novo" element={<Navigate to="/procedures/new" replace />} />
              <Route path="procedimentos/:id" element={<LegacyProcedimentoRedirect />} />
              <Route path="pocs/novo" element={<Navigate to="/pocs/new" replace />} />
              <Route path="rfis/novo" element={<Navigate to="/rfis/new" replace />} />
              <Route path="licitacoes" element={<Navigate to="/tenders" replace />} />
              <Route path="usuarios" element={<Navigate to="/users" replace />} />
              <Route path="minha-conta" element={<Navigate to="/my-account" replace />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </AuthProvider>
      )}
    </LanguageProvider>
  );
}
