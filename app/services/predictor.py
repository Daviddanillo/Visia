import logging
import warnings
from datetime import date, datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from prophet import Prophet
from prophet.diagnostics import cross_validation, performance_metrics
from sqlalchemy.orm import Session

from app.models.venda import Venda, UploadArquivo

# Suprimir logs verbosos do Prophet / cmdstanpy / Stan
logging.getLogger("prophet").setLevel(logging.WARNING)
logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
warnings.filterwarnings("ignore", category=FutureWarning)


# ---------------------------------------------------------------------------
# Helpers de calendário
# ---------------------------------------------------------------------------

def _calcular_pascoa(ano: int) -> date:
    a = ano % 19
    b = ano // 100
    c = ano % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741 — nomenclatura do algoritmo de Gauss
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


def _proximo_domingo(ref: date) -> date:
    d = ref
    while d.weekday() != 6:
        d += timedelta(days=1)
    return d


def _ultima_sexta_antes(ref: date) -> date:
    d = ref
    while d.weekday() != 4:
        d -= timedelta(days=1)
    return d


def _construir_feriados(anos: list) -> tuple:
    """
    Retorna:
      - holidays_df   : DataFrame no formato Prophet com janelas de efeito
                        (dias antes/depois também influenciam a previsão)
      - feriados_lookup: dict {ds_str: nome} somente das datas exatas,
                        usado para marcar is_holiday na resposta da API
    """
    registros = []
    feriados_lookup: dict = {}

    for ano in anos:
        pascoa = _calcular_pascoa(ano)

        # Tuplas: (data, nome, lower_window, upper_window)
        # lower_window < 0  → dias ANTES do feriado também têm efeito
        # upper_window > 0  → dias DEPOIS  do feriado também têm efeito
        entradas = [
            (pascoa - timedelta(days=48), "Carnaval",               -1,  1),
            (pascoa - timedelta(days=2),  "Sexta-feira Santa",       0,  0),
            (pascoa,                      "Páscoa",                  0,  0),
            (pascoa + timedelta(days=60), "Corpus Christi",          0,  0),
            (date(ano,  1,  1), "Ano Novo",                         -1,  1),
            (date(ano,  4, 21), "Tiradentes",                        0,  0),
            (date(ano,  5,  1), "Dia do Trabalho",                   0,  0),
            (date(ano,  6, 12), "Dia dos Namorados",                -2,  0),
            (date(ano,  9,  7), "Independência do Brasil",           0,  0),
            (date(ano, 10, 12), "Nossa Senhora Aparecida",           0,  0),
            (date(ano, 11,  2), "Finados",                           0,  0),
            (date(ano, 11, 15), "Proclamação da República",          0,  0),
            (date(ano, 11, 20), "Consciência Negra",                 0,  0),
            (date(ano, 12, 24), "Véspera de Natal",                  0,  0),
            (date(ano, 12, 25), "Natal",                            -3,  1),
            (date(ano, 12, 31), "Réveillon",                        -1,  0),
            (_proximo_domingo(date(ano, 5,  1)) + timedelta(days=7),
             "Dia das Mães", -7, 0),
            (_proximo_domingo(date(ano, 8,  1)) + timedelta(days=7),
             "Dia dos Pais", -7, 0),
            (_ultima_sexta_antes(date(ano, 11, 30)),
             "Black Friday", -3,  1),
        ]

        for d, nome, lower_w, upper_w in entradas:
            registros.append({
                "holiday":      nome,
                "ds":           pd.Timestamp(d),
                "lower_window": lower_w,
                "upper_window": upper_w,
            })
            feriados_lookup[d.strftime("%Y-%m-%d")] = nome

    return pd.DataFrame(registros), feriados_lookup


# ---------------------------------------------------------------------------
# Validação cruzada e acurácia
# ---------------------------------------------------------------------------

def _calcular_cv(model: Prophet, df: pd.DataFrame, dias: int) -> dict:
    n_days = int((df["ds"].max() - df["ds"].min()).days)
    min_initial = max(3 * dias, 90)
    if n_days < min_initial + dias:
        return {
            "disponivel": False,
            "motivo": f"Histórico de {n_days} dias insuficiente. São necessários ao menos {min_initial + dias} dias para validação cruzada.",
        }
    try:
        initial_days = max(min_initial, int(n_days * 0.6))
        period_days  = max(dias, 45)
        cv_df = cross_validation(
            model,
            initial=f"{initial_days} days",
            period=f"{period_days} days",
            horizon=f"{dias} days",
            parallel=None,
            disable_tqdm=True,
        )
        pm = performance_metrics(cv_df, rolling_window=1)

        mae      = round(float(pm["mae"].mean()), 2)
        mape_pct = round(float(pm["mape"].mean()) * 100, 2)
        rmse     = round(float(pm["rmse"].mean()), 2)
        coverage = round(float(pm["coverage"].mean()) * 100, 1)
        n_cortes = int(cv_df["cutoff"].nunique())

        pm["horizon_days"] = pm["horizon"].dt.days
        por_horizonte = (
            pm.groupby("horizon_days")[["mae", "mape", "rmse"]]
            .mean()
            .reset_index()
        )
        horizonte_list = [
            {
                "dia":  int(r["horizon_days"]),
                "mae":  round(float(r["mae"]), 2),
                "mape": round(float(r["mape"]) * 100, 2),
                "rmse": round(float(r["rmse"]), 2),
            }
            for _, r in por_horizonte.iterrows()
        ]
        return {
            "disponivel": True,
            "mae":       mae,
            "mape":      mape_pct,
            "rmse":      rmse,
            "coverage":  coverage,
            "n_cortes":  n_cortes,
            "horizonte": horizonte_list,
        }
    except Exception:
        return {"disponivel": False, "motivo": "Erro interno ao calcular métricas de acurácia."}


# ---------------------------------------------------------------------------
# Detecção de changepoints
# ---------------------------------------------------------------------------

def _extrair_changepoints(model: Prophet) -> list:
    if not hasattr(model, "changepoints") or len(model.changepoints) == 0:
        return []
    try:
        deltas = model.params["delta"].mean(axis=0)
        cp_df  = pd.DataFrame({"ds": model.changepoints.values, "delta": deltas})
        cp_df  = cp_df.assign(abs_delta=cp_df["delta"].abs())
        if cp_df.empty or cp_df["abs_delta"].max() == 0:
            return []
        # Top 8 por magnitude, depois filtra os que têm < 20% do delta máximo (ruído)
        cp_df = cp_df.sort_values("abs_delta", ascending=False).head(8)
        min_rel = cp_df["abs_delta"].max() * 0.20
        cp_df = cp_df[cp_df["abs_delta"] >= min_rel].drop("abs_delta", axis=1).sort_values("ds")
        return [
            {
                "ds":    row["ds"].strftime("%Y-%m-%d"),
                "ds_br": row["ds"].strftime("%d/%m/%Y"),
                "delta": round(float(row["delta"]), 4),
                "tipo":  "aceleracao" if row["delta"] > 0 else "desaceleracao",
            }
            for _, row in cp_df.iterrows()
        ]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Função principal de previsão
# ---------------------------------------------------------------------------

def gerar_previsao(
    usuario_id: int,
    db: Session,
    dias: int = 30,
    arquivo_id: Optional[int] = None,
    categoria: Optional[str] = None,
) -> dict:
    query = db.query(Venda).filter(Venda.usuario_id == usuario_id)
    if arquivo_id:
        query = query.filter(Venda.arquivo_id == arquivo_id)
    if categoria:
        query = query.filter(Venda.categoria == categoria)
    vendas = query.all()

    if len(vendas) < 5:
        if categoria:
            raise ValueError(
                f"Dados insuficientes para a categoria '{categoria}'. "
                "Mínimo de 5 registros necessários."
            )
        raise ValueError("Dados insuficientes. Mínimo de 5 registros necessários.")

    df = pd.DataFrame([{"ds": v.data_venda, "y": float(v.valor)} for v in vendas])
    df["ds"] = pd.to_datetime(df["ds"])
    df = df.groupby("ds")["y"].sum().reset_index().sort_values("ds")

    min_ano = df["ds"].dt.year.min()
    max_ano = (datetime.now() + timedelta(days=dias + 366)).year
    anos = list(range(min_ano, max_ano + 1))
    holidays_df, feriados_lookup = _construir_feriados(anos)

    # Parâmetros do Prophet:
    # - yearly_seasonality="auto" : ativa automaticamente se tiver ≥ 1 ano de dados
    # - weekly_seasonality="auto" : ativa automaticamente se tiver ≥ 2 semanas
    # - holidays=holidays_df      : feriados como regressores reais (afetam o yhat)
    # - interval_width=0.95       : intervalo de confiança de 95% que CRESCE com o horizonte
    # - changepoint_prior_scale   : flexibilidade da tendência (0.001=rígida … 0.5=muito flexível)
    model = Prophet(
        changepoint_prior_scale=0.05,
        seasonality_prior_scale=10.0,
        holidays_prior_scale=10.0,
        seasonality_mode="additive",
        yearly_seasonality="auto",
        weekly_seasonality="auto",
        daily_seasonality=False,
        holidays=holidays_df,
        interval_width=0.95,
    )

    model.fit(df)

    future   = model.make_future_dataframe(periods=dias, freq="D")
    forecast = model.predict(future)

    acuracia = _calcular_cv(model, df, dias)
    changepoints = _extrair_changepoints(model)

    tendencia = [
        {
            "ds":    row["ds"].strftime("%Y-%m-%d"),
            "ds_br": row["ds"].strftime("%d/%m/%Y"),
            "trend": round(float(row["trend"]), 2),
        }
        for _, row in forecast.iterrows()
    ]

    dias_semana_full = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    hist_fc = forecast[forecast["ds"] <= df["ds"].max()].copy()

    if "weekly" in forecast.columns and not hist_fc.empty:
        # Usa o efeito semanal aprendido pelo Prophet
        dow_effect = hist_fc.groupby(hist_fc["ds"].dt.dayofweek)["weekly"].mean()
        semanal = {
            nome: round(float(dow_effect.get(i, 0.0)), 4)
            for i, nome in enumerate(dias_semana_full)
        }
    else:
        # Fallback estatístico (poucos dados)
        ts = df.set_index("ds")["y"]
        overall_mean = float(ts.mean()) or 1.0
        dow_avg = ts.groupby(ts.index.dayofweek).mean()
        semanal = {
            nome: round(float(dow_avg.get(i, overall_mean)) - overall_mean, 2)
            for i, nome in enumerate(dias_semana_full)
        }

    meses = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
             "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

    if "yearly" in forecast.columns and not hist_fc.empty:
        month_effect = hist_fc.groupby(hist_fc["ds"].dt.month)["yearly"].mean()
        anual = [
            {"mes": nome, "valor": round(float(month_effect.get(i, 0.0)), 4)}
            for i, nome in enumerate(meses, 1)
        ]
    else:
        ts = df.set_index("ds")["y"]
        overall_mean = float(ts.mean()) or 1.0
        month_avg = ts.groupby(ts.index.month).mean()
        anual = [
            {"mes": nome, "valor": round(float(month_avg.get(i, overall_mean)) - overall_mean, 2)}
            for i, nome in enumerate(meses, 1)
        ]

    historico = [
        {
            "ds":    r["ds"].strftime("%Y-%m-%d"),
            "ds_br": r["ds"].strftime("%d/%m/%Y"),
            "y":     round(float(r["y"]), 2),
        }
        for _, r in df.iterrows()
    ]

    future_fc = forecast[forecast["ds"] > df["ds"].max()].copy()

    dias_semana_short = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    yhat_arr  = np.maximum(future_fc["yhat"].values.astype(float), 0)
    lower_arr = np.maximum(future_fc["yhat_lower"].values.astype(float), 0)
    upper_arr = future_fc["yhat_upper"].values.astype(float)

    # ── Limiares de alerta baseados em percentis (funciona para previsões suaves e voláteis) ──
    positive_yhats = yhat_arr[yhat_arr > 0]
    if len(positive_yhats) >= 4:
        median_yhat = float(np.median(positive_yhats))
        p25 = float(np.percentile(positive_yhats, 25))
        p75 = float(np.percentile(positive_yhats, 75))
    else:
        median_yhat = float(np.mean(yhat_arr)) if len(yhat_arr) > 0 else 0.0
        p25 = median_yhat * 0.8
        p75 = median_yhat * 1.2
    # Ignora dias com valor próximo de zero (artefacto do clip para 0)
    min_yhat = median_yhat * 0.05

    forecast_list = []
    for i, row in enumerate(future_fc.itertuples()):
        ds_str = row.ds.strftime("%Y-%m-%d")
        yhat   = float(yhat_arr[i])

        alert_type = None
        alert_pct  = None
        if yhat >= min_yhat and median_yhat > 0:
            pct = (yhat - median_yhat) / median_yhat * 100
            if yhat >= p75:
                alert_type, alert_pct = "alta", round(pct, 1)
            elif yhat <= p25:
                alert_type, alert_pct = "queda", round(pct, 1)

        feriado = feriados_lookup.get(ds_str)
        forecast_list.append({
            "ds":           ds_str,
            "ds_br":        row.ds.strftime("%d/%m/%Y"),
            "dia_semana":   dias_semana_short[row.ds.dayofweek],
            "yhat":         round(yhat, 2),
            "yhat_lower":   round(float(lower_arr[i]), 2),
            "yhat_upper":   round(float(upper_arr[i]), 2),
            "is_holiday":   feriado is not None,
            "holiday_name": feriado,
            "alert_type":   alert_type,
            "alert_pct":    alert_pct,
        })

    # ── Deduplica alertas consecutivos: mantém só o mais extremo em janelas de 7 dias ──
    for atype in ("alta", "queda"):
        idxs = [i for i, f in enumerate(forecast_list) if f["alert_type"] == atype]
        to_remove: set = set()
        seen: set = set()
        for i in idxs:
            if i in seen:
                continue
            base_ds = pd.Timestamp(forecast_list[i]["ds"])
            group = [
                j for j in idxs
                if j not in seen
                and abs((pd.Timestamp(forecast_list[j]["ds"]) - base_ds).days) < 7
            ]
            for j in group:
                seen.add(j)
            if len(group) > 1:
                best = (
                    max(group, key=lambda j: forecast_list[j]["yhat"]) if atype == "alta"
                    else min(group, key=lambda j: forecast_list[j]["yhat"])
                )
                for j in group:
                    if j != best:
                        to_remove.add(j)
        for i in to_remove:
            forecast_list[i]["alert_type"] = None
            forecast_list[i]["alert_pct"] = None

    # ── Limita a 5 alertas de cada tipo (os mais extremos) ──
    for atype in ("alta", "queda"):
        alert_idxs = [i for i, f in enumerate(forecast_list) if f["alert_type"] == atype]
        if len(alert_idxs) > 5:
            if atype == "alta":
                keep = set(sorted(alert_idxs, key=lambda i: forecast_list[i]["yhat"], reverse=True)[:5])
            else:
                keep = set(sorted(alert_idxs, key=lambda i: forecast_list[i]["yhat"])[:5])
            for i in alert_idxs:
                if i not in keep:
                    forecast_list[i]["alert_type"] = None
                    forecast_list[i]["alert_pct"] = None

    nome_arquivo = "Todos os dados"
    if arquivo_id:
        arq = db.query(UploadArquivo).filter(UploadArquivo.id == arquivo_id).first()
        if arq:
            nome_arquivo = arq.nome_arquivo
    if categoria:
        nome_arquivo = f"{nome_arquivo} · {categoria}"

    yhats            = [f["yhat"] for f in forecast_list]
    feriados_periodo = [f for f in forecast_list if f["is_holiday"]]
    quedas           = [f for f in forecast_list if f["alert_type"] == "queda"]
    altas            = [f for f in forecast_list if f["alert_type"] == "alta"]

    return {
        "arquivo_id":      arquivo_id,
        "nome_arquivo":    nome_arquivo,
        "categoria":       categoria,
        "dias_previstos":  dias,
        "total_historico": len(historico),
        "forecast":        forecast_list,
        "historico":       historico,
        "componentes": {
            "tendencia": tendencia,
            "semanal":   semanal,
            "anual":     anual,
        },
        "acuracia":    acuracia,
        "changepoints": changepoints,
        "resumo": {
            "media_previsao":      round(sum(yhats) / len(yhats), 2) if yhats else 0,
            "minimo":              round(min(yhats), 2) if yhats else 0,
            "maximo":              round(max(yhats), 2) if yhats else 0,
            "total_alertas_queda": len(quedas),
            "total_alertas_alta":  len(altas),
            "total_feriados":      len(feriados_periodo),
            "feriados_lista": [
                {"ds_br": f["ds_br"], "nome": f["holiday_name"]}
                for f in feriados_periodo
            ],
        },
    }


# ---------------------------------------------------------------------------
# Previsão POR CATEGORIA / PRODUTO
# ---------------------------------------------------------------------------

_DIAS_SEMANA_SHORT = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


def _prever_serie_categoria(
    serie: pd.DataFrame,
    dias: int,
    holidays_df: pd.DataFrame,
) -> tuple:
    """Ajusta um Prophet leve a uma série diária e devolve (forecast_fut, hist).

    `serie` deve ter colunas ds (datetime) e y. Retorna a porção futura do
    forecast (DataFrame) e o histórico agregado.
    """
    model = Prophet(
        changepoint_prior_scale=0.05,
        seasonality_mode="additive",
        yearly_seasonality="auto",
        weekly_seasonality="auto",
        daily_seasonality=False,
        holidays=holidays_df,
        interval_width=0.80,
    )
    model.fit(serie)
    future   = model.make_future_dataframe(periods=dias, freq="D")
    forecast = model.predict(future)
    fut = forecast[forecast["ds"] > serie["ds"].max()].copy()
    return fut, serie


def _insights_da_serie(categoria: str, fut: pd.DataFrame, max_insights: int = 3) -> list:
    """Detecta dias de alta/queda relevantes para uma categoria e gera frases."""
    yhat_arr = np.maximum(fut["yhat"].values.astype(float), 0)
    positivos = yhat_arr[yhat_arr > 0]
    if len(positivos) < 4:
        return []
    mediana = float(np.median(positivos))
    if mediana <= 0:
        return []
    p25 = float(np.percentile(positivos, 25))
    p75 = float(np.percentile(positivos, 75))

    candidatos = []
    for i, row in enumerate(fut.itertuples()):
        yhat = float(yhat_arr[i])
        if yhat < mediana * 0.05:
            continue
        pct = (yhat - mediana) / mediana * 100
        if yhat >= p75 and pct >= 8:
            tipo = "alta"
        elif yhat <= p25 and pct <= -8:
            tipo = "queda"
        else:
            continue
        candidatos.append({
            "ds":        row.ds.strftime("%Y-%m-%d"),
            "ds_br":     row.ds.strftime("%d/%m/%Y"),
            "dia_semana": _DIAS_SEMANA_SHORT[row.ds.dayofweek],
            "tipo":      tipo,
            "pct":       round(pct, 1),
            "yhat":      round(yhat, 2),
            "categoria": categoria,
        })

    # Deduplica em janelas de 7 dias, mantendo o mais extremo de cada tipo
    selecionados = []
    for tipo in ("alta", "queda"):
        grupo = [c for c in candidatos if c["tipo"] == tipo]
        grupo.sort(key=lambda c: abs(c["pct"]), reverse=True)
        usados: list = []
        for c in grupo:
            d = pd.Timestamp(c["ds"])
            if any(abs((d - pd.Timestamp(u["ds"])).days) < 7 for u in usados):
                continue
            usados.append(c)
            if len(usados) >= max_insights:
                break
        selecionados.extend(usados)

    selecionados.sort(key=lambda c: c["ds"])
    for c in selecionados:
        if c["tipo"] == "alta":
            frase, sinal = "aumento previsto de", "+"
        else:
            frase, sinal = "queda prevista de", ""
        c["texto"] = (
            f"{c['ds_br']} ({c['dia_semana']}): {frase} "
            f"{categoria} ({sinal}{c['pct']}%)"
        )
    return selecionados


def gerar_previsao_categorias(
    usuario_id: int,
    db: Session,
    dias: int = 30,
    arquivo_id: Optional[int] = None,
    max_categorias: int = 10,
) -> dict:
    """Gera previsões individuais por categoria/produto e insights consolidados."""
    query = db.query(Venda).filter(
        Venda.usuario_id == usuario_id,
        Venda.categoria.isnot(None),
    )
    if arquivo_id:
        query = query.filter(Venda.arquivo_id == arquivo_id)
    vendas = query.all()

    if not vendas:
        return {
            "disponivel": False,
            "motivo": "Esta base de dados não possui categorias. "
                      "Envie um CSV com uma coluna de categoria/produto "
                      "(ex.: 'Chocolate', 'Flores') para ver previsões por produto.",
            "dias_previstos": dias,
            "categorias": [],
            "insights": [],
        }

    df = pd.DataFrame([
        {"categoria": v.categoria, "ds": v.data_venda, "y": float(v.valor)}
        for v in vendas
    ])
    df["ds"] = pd.to_datetime(df["ds"])

    # Ranking de categorias por volume total
    totais = (
        df.groupby("categoria")["y"]
        .agg(total="sum", registros="count")
        .reset_index()
        .sort_values("total", ascending=False)
    )
    top_categorias = totais.head(max_categorias)["categoria"].tolist()

    # Feriados cobrindo todo o intervalo
    min_ano = int(df["ds"].dt.year.min())
    max_ano = (datetime.now() + timedelta(days=dias + 366)).year
    holidays_df, _ = _construir_feriados(list(range(min_ano, max_ano + 1)))

    categorias_out: list = []
    insights_globais: list = []

    for cat in top_categorias:
        sub = (
            df[df["categoria"] == cat]
            .groupby("ds")["y"].sum().reset_index().sort_values("ds")
        )
        media_hist = float(sub["y"].mean()) if len(sub) else 0.0
        registros  = int(totais.loc[totais["categoria"] == cat, "registros"].iloc[0])
        total_hist = float(totais.loc[totais["categoria"] == cat, "total"].iloc[0])

        item = {
            "categoria":             cat,
            "registros":             registros,
            "total_historico_valor": round(total_hist, 2),
            "media_historica":       round(media_hist, 2),
            "forecast":              [],
            "insights":              [],
        }

        if len(sub) >= 5:
            try:
                fut, _ = _prever_serie_categoria(sub, dias, holidays_df)
                yhat_fut = np.maximum(fut["yhat"].values.astype(float), 0)
                media_prev = float(np.mean(yhat_fut)) if len(yhat_fut) else 0.0
                item["forecast"] = [
                    {
                        "ds":    row.ds.strftime("%Y-%m-%d"),
                        "ds_br": row.ds.strftime("%d/%m/%Y"),
                        "yhat":  round(max(float(row.yhat), 0), 2),
                    }
                    for row in fut.itertuples()
                ]
                idx_pico = int(np.argmax(yhat_fut)) if len(yhat_fut) else 0
                item["pico"] = item["forecast"][idx_pico] if item["forecast"] else None
                ins = _insights_da_serie(cat, fut)
                item["insights"] = ins
                insights_globais.extend(ins)
            except Exception:
                media_prev = media_hist
                item["modelo"] = "fallback"
        else:
            # Poucos dados → fallback simples (média recente)
            recente = sub.tail(14)["y"].mean() if len(sub) else 0.0
            media_prev = float(recente) if not np.isnan(recente) else media_hist
            item["modelo"] = "fallback"

        item["media_prevista"] = round(media_prev, 2)
        if media_hist > 0:
            variacao = (media_prev - media_hist) / media_hist * 100
        else:
            variacao = 0.0
        item["variacao_pct"] = round(variacao, 1)
        if variacao >= 5:
            item["tendencia"] = "alta"
        elif variacao <= -5:
            item["tendencia"] = "queda"
        else:
            item["tendencia"] = "estavel"

        categorias_out.append(item)

    # ── Insights globais: ordena por data, limita aos mais relevantes ──
    insights_globais.sort(key=lambda c: (c["ds"], -abs(c["pct"])))
    insights_globais = insights_globais[:25]

    # ── Resumo: categoria em maior crescimento e maior volume ──
    resumo = {}
    if categorias_out:
        destaque = max(categorias_out, key=lambda c: c["variacao_pct"])
        maior_vol = max(categorias_out, key=lambda c: c["total_historico_valor"])
        queda = min(categorias_out, key=lambda c: c["variacao_pct"])
        resumo = {
            "categoria_destaque":      destaque["categoria"],
            "categoria_destaque_pct":  destaque["variacao_pct"],
            "categoria_maior_volume":  maior_vol["categoria"],
            "categoria_queda":         queda["categoria"] if queda["variacao_pct"] < 0 else None,
            "categoria_queda_pct":     queda["variacao_pct"] if queda["variacao_pct"] < 0 else None,
        }

    return {
        "disponivel":       True,
        "dias_previstos":   dias,
        "total_categorias": len(categorias_out),
        "categorias":       categorias_out,
        "insights":         insights_globais,
        "resumo":           resumo,
    }
