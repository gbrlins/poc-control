import { FormEvent, useEffect, useState } from "react";
import { api, ChaveGeminiStatus, ModeloGemini, User } from "../api";
import { useLanguage } from "../i18n";

export function MinhaConta({
  user,
  onUserAtualizado,
}: {
  user: User;
  onUserAtualizado: (user: User) => void;
}) {
  const { t } = useLanguage();
  const [apiKey, setApiKey] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [removendo, setRemovendo] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [salvo, setSalvo] = useState(false);

  const [modelo, setModelo] = useState(user.gemini_model ?? "");
  const [salvandoModelo, setSalvandoModelo] = useState(false);
  const [modeloSalvo, setModeloSalvo] = useState(false);
  const [modelosDisponiveis, setModelosDisponiveis] = useState<ModeloGemini[] | null>(null);
  const [carregandoModelos, setCarregandoModelos] = useState(true);
  const [erroModelos, setErroModelos] = useState<string | null>(null);

  const [statusChave, setStatusChave] = useState<ChaveGeminiStatus | null>(null);
  const [testando, setTestando] = useState(false);
  const [resultadoTeste, setResultadoTeste] = useState<{ ok: boolean; mensagem: string | null } | null>(null);

  function recarregarStatusChave() {
    api.statusChaveGemini().then(setStatusChave).catch(() => setStatusChave(null));
  }

  useEffect(() => {
    api
      .listarModelosGemini()
      .then(setModelosDisponiveis)
      .catch(() => setErroModelos(t("minhaConta.modeloErroListar")))
      .finally(() => setCarregandoModelos(false));
    recarregarStatusChave();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function testarChave() {
    setTestando(true);
    setResultadoTeste(null);
    try {
      setResultadoTeste(await api.testarChaveGemini());
    } catch {
      setResultadoTeste({ ok: false, mensagem: t("minhaConta.chaveTesteErro") });
    } finally {
      setTestando(false);
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setErro(null);
    setSalvando(true);
    try {
      const atualizado = await api.salvarChaveGemini(apiKey.trim());
      onUserAtualizado(atualizado);
      setApiKey("");
      setSalvo(true);
      setResultadoTeste(null);
      recarregarStatusChave();
      window.setTimeout(() => setSalvo(false), 3000);
    } catch {
      setErro(t("minhaConta.erroSalvar"));
    } finally {
      setSalvando(false);
    }
  }

  async function remover() {
    setRemovendo(true);
    try {
      const atualizado = await api.removerChaveGemini();
      onUserAtualizado(atualizado);
      setResultadoTeste(null);
      recarregarStatusChave();
    } finally {
      setRemovendo(false);
    }
  }

  async function salvarModelo(e: FormEvent) {
    e.preventDefault();
    setSalvandoModelo(true);
    try {
      const valor = modelo.trim();
      const atualizado = valor ? await api.salvarModeloGemini(valor) : await api.removerModeloGemini();
      onUserAtualizado(atualizado);
      setModeloSalvo(true);
      window.setTimeout(() => setModeloSalvo(false), 3000);
    } finally {
      setSalvandoModelo(false);
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>{t("minhaConta.titulo")}</h1>
      </div>

      <div className="card">
        <h2>{t("minhaConta.chaveGemini")}</h2>
        <p className="field-hint">{t("minhaConta.chaveHint")}</p>

        {user.tem_gemini_key ? (
          <p className="alert alert-success" style={{ marginBottom: 16 }}>
            {t("minhaConta.temChave")}
          </p>
        ) : (
          <p className="alert alert-warning" style={{ marginBottom: 16 }}>
            {t("minhaConta.semChave")}
          </p>
        )}

        {statusChave && (
          <div className="field-box" style={{ marginBottom: 16, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
            <span className="muted" style={{ fontSize: 13 }}>
              {t("minhaConta.chaveEmUso")} <code>{statusChave.chave_mascarada ?? t("minhaConta.chaveOrigemNenhuma")}</code>
              {statusChave.chave_mascarada && (
                <>
                  {" "}
                  (
                  {statusChave.origem === "pessoal"
                    ? t("minhaConta.chaveOrigemPessoal")
                    : t("minhaConta.chaveOrigemAmbiente")}
                  )
                </>
              )}
            </span>
            <button type="button" className="btn btn-outline btn-sm" onClick={() => void testarChave()} disabled={testando || !statusChave.chave_mascarada}>
              {testando ? t("minhaConta.chaveTestando") : t("minhaConta.chaveTestar")}
            </button>
            {resultadoTeste && (
              <span className={resultadoTeste.ok ? "pill pill-ok" : "pill pill-warn"}>
                {resultadoTeste.ok ? t("minhaConta.chaveTesteOk") : resultadoTeste.mensagem}
              </span>
            )}
          </div>
        )}

        <form onSubmit={handleSubmit} className="form">
          <div className="field">
            <label htmlFor="gemini-key">
              {user.tem_gemini_key ? t("minhaConta.substituirChave") : t("minhaConta.cadastrarChave")}
            </label>
            <input
              id="gemini-key"
              type="password"
              className="input"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="AIza..."
              autoComplete="off"
              minLength={10}
              required
            />
            <p className="field-hint">
              {t("minhaConta.gereSua")}{" "}
              <a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer">
                aistudio.google.com/apikey
              </a>
              . {t("minhaConta.chaveArmazenada")}
            </p>
          </div>
          {erro && <p className="alert alert-error">{erro}</p>}
          <div style={{ display: "flex", gap: 8 }}>
            <button type="submit" className="btn btn-primary" disabled={salvando || !apiKey.trim()}>
              {salvando ? t("common.salvando") : salvo ? t("minhaConta.salva") : t("minhaConta.salvarChave")}
            </button>
            {user.tem_gemini_key && (
              <button type="button" className="btn btn-secondary" onClick={remover} disabled={removendo}>
                {removendo ? t("minhaConta.removendo") : t("minhaConta.removerChave")}
              </button>
            )}
          </div>
        </form>
      </div>

      <div className="card">
        <h2>{t("minhaConta.modeloGemini")}</h2>
        <p className="field-hint">{t("minhaConta.modeloHint")}</p>

        <form onSubmit={salvarModelo} className="form">
          <div className="field">
            <label htmlFor="gemini-model">{t("minhaConta.modeloLabel")}</label>
            {erroModelos ? (
              <input
                id="gemini-model"
                type="text"
                className="input"
                value={modelo}
                onChange={(e) => setModelo(e.target.value)}
                placeholder="gemini-3.8-flash"
                autoComplete="off"
              />
            ) : (
              <select
                id="gemini-model"
                className="input"
                value={modelo}
                onChange={(e) => setModelo(e.target.value)}
                disabled={carregandoModelos}
              >
                <option value="">{t("minhaConta.usarDefault")}</option>
                {modelosDisponiveis?.map((m) => (
                  <option key={m.nome} value={m.nome}>
                    {m.nome_exibicao} ({m.nome})
                  </option>
                ))}
                {modelo && modelosDisponiveis && !modelosDisponiveis.some((m) => m.nome === modelo) && (
                  <option value={modelo}>{modelo}</option>
                )}
              </select>
            )}
            <p className="field-hint">
              {erroModelos ?? (carregandoModelos ? t("minhaConta.modeloCarregando") : t("minhaConta.modeloVazioHint"))}
            </p>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button type="submit" className="btn btn-primary" disabled={salvandoModelo}>
              {salvandoModelo ? t("common.salvando") : modeloSalvo ? t("minhaConta.salva") : t("common.salvar")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
