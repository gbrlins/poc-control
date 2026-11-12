import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError, ProcedimentoDetail } from "@/api";
import { DangerZone } from "@/components/DangerZone";
import { useLanguage } from "@/i18n";
import { OrigemChip, ProcedimentoConteudo } from "../components/ProcedimentoConteudo";

export function ProcedimentoView() {
  const { t, lang } = useLanguage();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [procedimento, setProcedimento] = useState<ProcedimentoDetail | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [validando, setValidando] = useState(false);
  const [erroValidar, setErroValidar] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    api
      .obterProcedimento(id, lang)
      .then(setProcedimento)
      .catch(() => setErro(t("procedimentoView.erroCarregar")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, lang]);

  if (erro) return <p className="alert alert-error">{erro}</p>;
  if (!procedimento) return <p className="muted">{t("common.carregando")}</p>;

  async function validar() {
    setValidando(true);
    setErroValidar(null);
    try {
      await api.validarProcedimento(procedimento!.id);
      setProcedimento({ ...procedimento!, status: "validado" });
    } catch (e) {
      setErroValidar(e instanceof ApiError ? e.message : t("procedimentoView.erroValidar"));
    } finally {
      setValidando(false);
    }
  }

  return (
    <div>
      <button type="button" className="btn btn-secondary" style={{ marginBottom: 16 }} onClick={() => navigate("/procedimentos")}>
        {t("procedimentoView.voltar")}
      </button>

      <div className="page-header">
        <h1>{procedimento.titulo}</h1>
        <div style={{ display: "flex", gap: 8 }}>
          <OrigemChip origem={procedimento.origem_conhecimento} />
          {procedimento.gerado_por_ia && <span className="chip">{t("procedimentoView.geradoPorIa")}</span>}
          <span className={`badge badge-${procedimento.status}`}>{procedimento.status}</span>
        </div>
      </div>

      {procedimento.status === "rascunho" && (
        <div className="alert alert-warning" style={{ marginBottom: 16 }}>
          <p style={{ marginTop: 0 }}>{t("procedimentoView.avisoRascunho")}</p>
          <button type="button" className="btn btn-primary" onClick={() => void validar()} disabled={validando}>
            {validando ? t("common.salvando") : t("procedimentoView.marcarValidado")}
          </button>
          {erroValidar && (
            <p className="alert alert-error" style={{ marginTop: 8 }}>
              {erroValidar}
            </p>
          )}
        </div>
      )}

      <ProcedimentoConteudo procedimento={procedimento} />

      <DangerZone
        tipo="procedimentos"
        id={procedimento.id}
        responsavelId={procedimento.responsavel_id}
        responsavelEmail={procedimento.responsavel_email}
        onResponsavelAtualizado={(responsavelId, responsavelEmail) =>
          setProcedimento({ ...procedimento, responsavel_id: responsavelId, responsavel_email: responsavelEmail })
        }
        onExcluido={() => navigate("/procedimentos")}
      />
    </div>
  );
}
