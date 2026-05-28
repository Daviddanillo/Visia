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
    l = (32 + 2 * e + 2 * i - h - k) % 7
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
        cp_df  = cp_df[cp_df["delta"].abs() > 0.005]
        if cp_df.empty:
            return []
        cp_df = (
            cp_df
            .assign(abs_delta=cp_df["delta"].abs())
            .sort_values("abs_delta", ascending=False)
            .head(8)
            .drop("abs_delta", axis=1)
            .sort_values("ds")
        )
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
) -> dict:
    # ---- Carregar dados do banco ----
    query = db.query(Venda).filter(Venda.usuario_id == usuario_id)
    if arquivo_id:
        query = query.filter(Venda.arquivo_id == arquivo_id)
    vendas = query.all()

    if len(vendas) < 5:
        raise ValueError("Dados insuficientes. Mínimo de 5 registros necessários.")

    df = pd.DataFrame([{"ds": v.data_venda, "y": float(v.valor)} for v in vendas])
    df["ds"] = pd.to_datetime(df["ds"])
    # Agrupa por dia (suma múltiplas vendas no mesmo dia)
    df = df.groupby("ds")["y"].sum().reset_index().sort_values("ds")

    # ---- Construir feriados ----
    min_ano = df["ds"].dt.year.min()
    max_ano = (datetime.now() + timedelta(days=dias + 366)).year
    anos = list(range(min_ano, max_ano + 1))
    holidays_df, feriados_lookup = _construir_feriados(anos)

    # ---- Treinar Prophet ----
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

    # ---- Cross-validation e acurácia ----
    acuracia = _calcular_cv(model, df, dias)

    # ---- Changepoints significativos ----
    changepoints = _extrair_changepoints(model)

    # ---- Componente de tendência (histórico + futuro) ----
    tendencia = [
        {
            "ds":    row["ds"].strftime("%Y-%m-%d"),
            "ds_br": row["ds"].strftime("%d/%m/%Y"),
            "trend": round(float(row["trend"]), 2),
        }
        for _, row in forecast.iterrows()
    ]

    # ---- Sazonalidade semanal ----
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

    # ---- Sazonalidade anual ----
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

    # ---- Histórico ----
    historico = [
        {
            "ds":    r["ds"].strftime("%Y-%m-%d"),
            "ds_br": r["ds"].strftime("%d/%m/%Y"),
            "y":     round(float(r["y"]), 2),
        }
        for _, r in df.iterrows()
    ]

    # ---- Previsão futura ----
    future_fc = forecast[forecast["ds"] > df["ds"].max()].copy()

    dias_semana_short = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    yhat_arr  = np.maximum(future_fc["yhat"].values.astype(float), 0)
    lower_arr = np.maximum(future_fc["yhat_lower"].values.astype(float), 0)
    upper_arr = future_fc["yhat_upper"].values.astype(float)

    # Média móvel de 7 dias usada para detectar alertas de alta/queda
    rolling_7 = pd.Series(yhat_arr).rolling(7, center=True, min_periods=1).mean().values

    forecast_list = []
    for i, row in enumerate(future_fc.itertuples()):
        ds_str = row.ds.strftime("%Y-%m-%d")
        yhat   = float(yhat_arr[i])
        roll   = float(rolling_7[i])

        alert_type = None
        alert_pct  = None
        if roll > 0:
            pct = (yhat - roll) / roll * 100
            if pct <= -20:
                alert_type, alert_pct = "queda", round(pct, 1)
            elif pct >= 25:
                alert_type, alert_pct = "alta", round(pct, 1)

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

    # ---- Nome do arquivo ----
    nome_arquivo = "Todos os dados"
    if arquivo_id:
        arq = db.query(UploadArquivo).filter(UploadArquivo.id == arquivo_id).first()
        if arq:
            nome_arquivo = arq.nome_arquivo

    # ---- Resumo ----
    yhats            = [f["yhat"] for f in forecast_list]
    feriados_periodo = [f for f in forecast_list if f["is_holiday"]]
    quedas           = [f for f in forecast_list if f["alert_type"] == "queda"]
    altas            = [f for f in forecast_list if f["alert_type"] == "alta"]

    return {
        "arquivo_id":      arquivo_id,
        "nome_arquivo":    nome_arquivo,
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
