import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, ProcedimentoDetail } from "@/api";
import { rotuloCategoria } from "@/categorias";
import { DangerZone } from "@/components/DangerZone";
import { useLanguage } from "@/i18n";

export function ProcedimentoView() {
  const { t, lang } = useLanguage();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [procedimento, setProcedimento] = useState<ProcedimentoDetail | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    api
      .obterProcedimento(id)
      .then(setProcedimento)
      .catch(() => setErro(t("procedimentoView.erroCarregar")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (erro) return <p className="alert alert-error">{erro}</p>;
  if (!procedimento) return <p className="muted">{t("common.carregando")}</p>;

  return (
    <div>
      <div className="page-header">
        <h1>{procedimento.titulo}</h1>
        <span className={`badge badge-${procedimento.status}`}>{procedimento.status}</span>
      </div>

      <div className="card">
        <p>
          <strong>{t("procedimentoView.cliente")}</strong> {procedimento.cliente_origem ?? "—"} &nbsp;·&nbsp;{" "}
          <strong>{t("procedimentoView.versao")}</strong> {procedimento.versao}
        </p>
        <p>
          <strong>{t("procedimentoView.tags")}</strong> {procedimento.tags.join(", ") || "—"}
        </p>
        <p>
          <strong>{t("procedimentoView.categorias")}</strong>{" "}
          {procedimento.categorias.length > 0
            ? procedimento.categorias.map((c) => (
                <span key={c} className="chip" style={{ marginRight: 6 }}>
                  {c} — {rotuloCategoria(c, lang)}
                </span>
              ))
            : "—"}
        </p>
      </div>

      <div className="card">
        <h2>{t("procedimentoView.secoesIndexadas")}</h2>
        <ul className="secoes-list">
          {procedimento.secoes.map((s, i) => (
            <li key={i} className={s.heading_level === 3 ? "sub" : undefined}>
              {s.heading_title}
            </li>
          ))}
        </ul>
      </div>

      <div className="card">
        <h2>{t("procedimentoView.conteudoOriginal")}</h2>
        <iframe
          title={procedimento.titulo}
          sandbox="allow-same-origin"
          srcDoc={procedimento.html_original}
          className="html-frame"
        />
      </div>

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
