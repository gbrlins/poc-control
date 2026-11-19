import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation, useParams } from "react-router-dom";
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
import { ProcedimentoImportarJson } from "./features/executar-poc/pages/ProcedimentoImportarJson";
import { ProcedimentoView } from "./features/executar-poc/pages/ProcedimentoView";
import { Pocs } from "./features/executar-poc/pages/Pocs";
import { PocUpload } from "./features/executar-poc/pages/PocUpload";
import { PocDetail } from "./features/executar-poc/pages/PocDetail";
import { PlanPoc } from "./features/planejar-poc/pages/PlanPoc";
import { Rfis } from "./features/rfi/pages/Rfis";
import { RfiUpload } from "./features/rfi/pages/RfiUpload";
import { RfiDetail } from "./features/rfi/pages/RfiDetail";
import { Licitacoes } from "./features/licitacoes/pages/Licitacoes";

// Redireciona um caminho antigo (em português) para o novo mantendo ?query e #hash: links como /planejar?open=<id>&readonly=1
// ou ?import=doc carregam a ação pedida, e perdê-los abriria o planejador numa etapa qualquer.
function Redirecionar({ para }: { para: string }) {
  const { search, hash } = useLocation();
  return <Navigate to={`${para}${search}${hash}`} replace />;
}

function LegacyProcedimentoRedirect() {
  const { id } = useParams<{ id: string }>();
  return <Redirecionar para={`/procedures/${id}`} />;
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
              <Route path="procedures/import-json" element={<ProcedimentoImportarJson />} />
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
              <Route path="planejar" element={<Redirecionar para="/plan" />} />
              <Route path="procedimentos" element={<Redirecionar para="/procedures" />} />
              <Route path="procedimentos/novo" element={<Redirecionar para="/procedures/new" />} />
              <Route path="procedimentos/:id" element={<LegacyProcedimentoRedirect />} />
              <Route path="pocs/novo" element={<Redirecionar para="/pocs/new" />} />
              <Route path="rfis/novo" element={<Redirecionar para="/rfis/new" />} />
              <Route path="licitacoes" element={<Redirecionar para="/tenders" />} />
              <Route path="usuarios" element={<Redirecionar para="/users" />} />
              <Route path="minha-conta" element={<Redirecionar para="/my-account" />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </AuthProvider>
      )}
    </LanguageProvider>
  );
}
