import { useState } from "react";
import { ApiError, PreviaExclusao, TipoRecurso, api } from "@/api";
import { useCurrentUser } from "@/auth";
import { useLanguage } from "@/i18n";

interface Props {
  tipo: TipoRecurso;
  id: string;
  responsavelId: string | null;
  responsavelEmail: string | null;
  onResponsavelAtualizado: (responsavelId: string, responsavelEmail: string) => void;
  onExcluido: () => void;
}

// Dono + exclusão permanente (ADR 4) -- compartilhado entre PocDetail, RfiDetail e
// ProcedimentoView, já que as três regras de backend são idênticas (app/exclusao.py).
export function DangerZone({ tipo, id, responsavelId, responsavelEmail, onResponsavelAtualizado, onExcluido }: Props) {
  const { t } = useLanguage();
  const user = useCurrentUser();
  const souDono = responsavelId === user.id;
  const semDono = responsavelId === null;

  const [emailTransferencia, setEmailTransferencia] = useState("");
  const [erroResponsavel, setErroResponsavel] = useState<string | null>(null);
  const [processandoResponsavel, setProcessandoResponsavel] = useState(false);

  const [previa, setPrevia] = useState<PreviaExclusao | null>(null);
  const [carregandoPrevia, setCarregandoPrevia] = useState(false);
  const [tituloConfirmacao, setTituloConfirmacao] = useState("");
  const [erroExclusao, setErroExclusao] = useState<string | null>(null);
  const [excluindo, setExcluindo] = useState(false);

  async function assumir() {
    setProcessandoResponsavel(true);
    setErroResponsavel(null);
    try {
      await api.definirResponsavel(tipo, id, user.id);
      onResponsavelAtualizado(user.id, user.email);
    } catch {
      setErroResponsavel(t("dangerZone.erroResponsavel"));
    } finally {
      setProcessandoResponsavel(false);
    }
  }

  async function transferir() {
    const email = emailTransferencia.trim();
    if (!email) return;
    setProcessandoResponsavel(true);
    setErroResponsavel(null);
    try {
      const alvo = await api.lookupUsuario(email);
      await api.definirResponsavel(tipo, id, alvo.id);
      onResponsavelAtualizado(alvo.id, alvo.email);
      setEmailTransferencia("");
    } catch (e) {
      setErroResponsavel(e instanceof ApiError && e.status === 404 ? t("dangerZone.usuarioNaoEncontrado") : t("dangerZone.erroTransferir"));
    } finally {
      setProcessandoResponsavel(false);
    }
  }

  async function abrirExclusao() {
    setCarregandoPrevia(true);
    setErroExclusao(null);
    try {
      setPrevia(await api.previaExclusao(tipo, id));
    } catch {
      setErroExclusao(t("dangerZone.erroPrevia"));
    } finally {
      setCarregandoPrevia(false);
    }
  }

  async function confirmarExclusao() {
    setExcluindo(true);
    setErroExclusao(null);
    try {
      await api.excluir(tipo, id, tituloConfirmacao);
      onExcluido();
    } catch (e) {
      setErroExclusao(e instanceof ApiError ? e.message : t("dangerZone.erroExcluir"));
    } finally {
      setExcluindo(false);
    }
  }

  return (
    <div className="card danger-zone">
      <h2>{t("dangerZone.titulo")}</h2>

      <p>
        <strong>{t("dangerZone.dono")}</strong>{" "}
        {semDono ? t("dangerZone.semDono") : responsavelEmail ?? responsavelId}
      </p>

      {semDono && (
        <button className="btn btn-secondary" onClick={assumir} disabled={processandoResponsavel}>
          {t("dangerZone.assumir")}
        </button>
      )}

      {souDono && (
        <div className="field" style={{ maxWidth: 420 }}>
          <label>{t("dangerZone.transferirPara")}</label>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              className="input"
              type="email"
              value={emailTransferencia}
              onChange={(e) => setEmailTransferencia(e.target.value)}
              placeholder="colega@empresa.com"
            />
            <button className="btn btn-secondary" onClick={transferir} disabled={processandoResponsavel}>
              {t("dangerZone.transferir")}
            </button>
          </div>
        </div>
      )}

      {erroResponsavel && <p className="alert alert-error">{erroResponsavel}</p>}

      <hr style={{ margin: "20px 0", border: "none", borderTop: "1px solid var(--color-danger)" }} />

      {!previa ? (
        <button className="btn btn-danger" onClick={abrirExclusao} disabled={carregandoPrevia}>
          {carregandoPrevia ? t("common.carregando") : t("dangerZone.excluirPermanentemente")}
        </button>
      ) : (
        <div>
          {!previa.podeExcluir && (
            <p className="alert alert-error">
              {semDono ? t("dangerZone.precisaAssumir") : t("dangerZone.somenteDonoExclui")}
            </p>
          )}

          <ul>
            {Object.entries(previa.contagens).map(([chave, valor]) => (
              <li key={chave}>
                {t(`dangerZone.contagem.${chave}`)}: {valor}
              </li>
            ))}
          </ul>

          {previa.procedimentosQuePermanecem.length > 0 && (
            <p>
              {t("dangerZone.procedimentosQuePermanecem")}:{" "}
              {previa.procedimentosQuePermanecem.map((p) => p.titulo).join(", ")}
            </p>
          )}
          {previa.vinculosQuePerdemProcedimento.length > 0 && (
            <p>
              {t("dangerZone.vinculosQuePerdem")}:{" "}
              {previa.vinculosQuePerdemProcedimento.map((v) => v.titulo).join(", ")}
            </p>
          )}

          {previa.podeExcluir && (
            <div className="field" style={{ maxWidth: 420 }}>
              <label>{t("dangerZone.digiteTitulo").replace("{titulo}", previa.titulo)}</label>
              <input
                className="input"
                value={tituloConfirmacao}
                onChange={(e) => setTituloConfirmacao(e.target.value)}
              />
              <button
                className="btn btn-danger"
                onClick={confirmarExclusao}
                disabled={excluindo || tituloConfirmacao.trim() !== previa.titulo}
              >
                {excluindo ? t("common.salvando") : t("dangerZone.confirmarExclusao")}
              </button>
            </div>
          )}

          {erroExclusao && <p className="alert alert-error">{erroExclusao}</p>}
        </div>
      )}
    </div>
  );
}
