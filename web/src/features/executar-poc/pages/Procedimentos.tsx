import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, OrigemConhecimento, ProcedimentoDetail, ProcedimentoListItem } from "@/api";
import { CODIGOS_CATEGORIA, rotuloCategoria } from "@/categorias";
import { useLanguage } from "@/i18n";
import { toggleInSet } from "@/toggleInSet";
import { OrigemChip, ProcedimentoConteudo } from "../components/ProcedimentoConteudo";
import { SincronizarProcedimentos } from "../components/SincronizarProcedimentos";

const ORIGENS: OrigemConhecimento[] = ["manual", "poc", "rfi"];

export function Procedimentos() {
  const { t, lang } = useLanguage();
  const [itens, setItens] = useState<ProcedimentoListItem[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [filtroCategorias, setFiltroCategorias] = useState<Set<string>>(new Set());
  const [filtroOrigens, setFiltroOrigens] = useState<Set<OrigemConhecimento>>(new Set());
  const [syncDisponivel, setSyncDisponivel] = useState(false);
  const [mostrarSync, setMostrarSync] = useState(false);

  function carregar() {
    api
      .listarProcedimentos()
      .then(setItens)
      .catch(() => setErro(t("procedimentos.erroCarregar")));
  }

  useEffect(() => {
    carregar();
    api
      .syncConfig()
      .then((r) => setSyncDisponivel(r.configurado))
      .catch(() => setSyncDisponivel(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function alternarFiltro(codigo: string) {
    setFiltroCategorias((atual) => toggleInSet(atual, codigo));
  }

  function alternarOrigem(origem: OrigemConhecimento) {
    setFiltroOrigens((atual) => toggleInSet(atual, origem));
  }

  const filtrados = useMemo(() => {
    if (!itens) return [];
    return itens
      .filter((p) => filtroCategorias.size === 0 || p.categorias.some((c) => filtroCategorias.has(c)))
      .filter((p) => filtroOrigens.size === 0 || filtroOrigens.has(p.origem_conhecimento));
  }, [itens, filtroCategorias, filtroOrigens]);

  return (
    <div>
      <div className="page-header">
        <h1>{t("procedimentos.titulo")}</h1>
        <div style={{ display: "flex", gap: 8 }}>
          {syncDisponivel && (
            <button type="button" className="btn btn-secondary" onClick={() => setMostrarSync(true)}>
              {t("procedimentos.sincronizar")}
            </button>
          )}
          <Link to="/procedimentos/novo" className="btn btn-primary">
            {t("procedimentos.novoProcedimento")}
          </Link>
        </div>
      </div>

      {mostrarSync && itens && (
        <SincronizarProcedimentos
          locais={itens}
          onClose={() => setMostrarSync(false)}
          onMudou={carregar}
        />
      )}

      {erro && <p className="alert alert-error">{erro}</p>}
      {itens === null && !erro && <p className="muted">{t("common.carregando")}</p>}

      {itens && itens.length > 0 && (
        <div className="card" style={{ marginBottom: 20 }}>
          <label style={{ display: "block", marginBottom: 8 }}>{t("procedimentos.filtroOrigem")}</label>
          <div className="chip-filter-group" style={{ marginBottom: 14 }}>
            {ORIGENS.map((origem) => (
              <button
                key={origem}
                type="button"
                className={`chip-filter${filtroOrigens.has(origem) ? " active" : ""}`}
                onClick={() => alternarOrigem(origem)}
              >
                {t(`procedimentos.origem${origem[0].toUpperCase()}${origem.slice(1)}`)}
              </button>
            ))}
          </div>
          <label style={{ display: "block", marginBottom: 8 }}>{t("procedimentos.filtroCategoria")}</label>
          <div className="chip-filter-group">
            {CODIGOS_CATEGORIA.map((codigo) => (
              <button
                key={codigo}
                type="button"
                className={`chip-filter${filtroCategorias.has(codigo) ? " active" : ""}`}
                onClick={() => alternarFiltro(codigo)}
              >
                {codigo} — {rotuloCategoria(codigo, lang)}
              </button>
            ))}
          </div>
        </div>
      )}

      {itens && itens.length === 0 && <div className="card empty-state">{t("procedimentos.nenhum")}</div>}

      {itens && itens.length > 0 && (
        <div className="card">
          {filtrados.length === 0 && <div className="empty-state">{t("procedimentos.nenhumComFiltro")}</div>}
          {filtrados.map((p) => (
            <ProcedimentoRow key={p.id} item={p} />
          ))}
        </div>
      )}
    </div>
  );
}

function ProcedimentoRow({ item }: { item: ProcedimentoListItem }) {
  const { t, lang } = useLanguage();
  const [open, setOpen] = useState(false);
  const [detalhe, setDetalhe] = useState<ProcedimentoDetail | null>(null);
  const [carregando, setCarregando] = useState(false);

  useEffect(() => {
    if (!open || detalhe) return;
    setCarregando(true);
    api
      .obterProcedimento(item.id)
      .then(setDetalhe)
      .finally(() => setCarregando(false));
  }, [open, detalhe, item.id]);

  return (
    <div className={open ? "item-row open" : "item-row"}>
      <div className="procedimentos-row-head" onClick={() => setOpen((v) => !v)}>
        <span className="item-titulo item-titulo-truncado" title={item.titulo}>
          {item.titulo}
        </span>
        <OrigemChip origem={item.origem_conhecimento} />
        {item.categorias.length > 0 && (
          <span className="muted" style={{ fontSize: 12 }}>
            {item.categorias.map((c) => rotuloCategoria(c, lang)).join(", ")}
          </span>
        )}
        <span className="muted" style={{ fontSize: 12 }}>
          {item.cliente_origem ?? "—"}
        </span>
        <span className="muted" style={{ fontSize: 12 }}>
          {item.responsavel_email ?? t("procedimentos.semDono")}
        </span>
        <span className={`badge badge-${item.status}`}>{item.status}</span>
      </div>

      {open && (
        <div className="item-row-body">
          {carregando && <p className="muted">{t("common.carregando")}</p>}
          {detalhe && (
            <>
              <ProcedimentoConteudo procedimento={detalhe} />
              <Link to={`/procedimentos/${item.id}`} className="btn btn-secondary">
                {t("procedimentos.abrirTelaCheia")}
              </Link>
            </>
          )}
        </div>
      )}
    </div>
  );
}
