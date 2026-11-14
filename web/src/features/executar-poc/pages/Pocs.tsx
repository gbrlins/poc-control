import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, PocListItem } from "@/api";
import { useLanguage } from "@/i18n";
import { PocsTable } from "../components/PocsTable";
import { PocFiltros, usePocFiltros } from "../components/PocFiltros";

export function Pocs() {
  const { t } = useLanguage();
  const [itens, setItens] = useState<PocListItem[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const { filtros, setFiltros, filtrados, responsaveis } = usePocFiltros(itens);

  useEffect(() => {
    api
      .listarPocs()
      .then(setItens)
      .catch(() => setErro(t("pocs.erroCarregar")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div>
      <div className="page-header">
        <h1>{t("pocs.titulo")}</h1>
        <Link to="/pocs/new" className="btn btn-primary">
          {t("pocs.novaPoc")}
        </Link>
      </div>

      {erro && <p className="alert alert-error">{erro}</p>}
      {itens === null && !erro && <p className="muted">{t("common.carregando")}</p>}

      {itens && (
        <>
          <PocFiltros filtros={filtros} setFiltros={setFiltros} responsaveis={responsaveis} />
          <PocsTable itens={filtrados ?? []} />
        </>
      )}
    </div>
  );
}
