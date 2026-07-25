"""
Fantasy Draft
=============
Liga de fantasy (draft) do Cartola: 6 participantes disputam 3 confrontos por
rodada, seguindo a tabela do turno.

- Ao vivo: parciais dos confrontos da rodada, pontuacao pelos pesos da liga
  (scouts_pontuacao.json): Sigma(scout x peso).
- Historico: cada rodada arquivada, lida da planilha.
- Classificacao do turno: V, E, D, pontos feitos e sofridos.
- Configuracao (participantes, tabela de confrontos, range, senhas) fica na
  planilha do Google Sheets (abas participantes / confrontos / config).

Fonte de dados: API publica do Cartola (Brasileirao).

Rodar com:  streamlit run parciais.py
"""

import json
import os
import pathlib
import re
import time
from html import escape
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
import streamlit as st

BASE_DIR = pathlib.Path(__file__).resolve().parent

API_BASE = "https://api.cartola.globo.com"
ESCALACAO_FILE = str(BASE_DIR / "escalacao_salva.json")
SCOUTS_PESOS_FILE = str(BASE_DIR / "scouts_pontuacao.json")
PARTIDAS_PATH = "/partidas"

MAX_CONFRONTOS = 3

# --- Configuração padrão (semeada na planilha na 1ª execução; editável lá depois) ---
PARTICIPANTES_PADRAO = [
    "Rafael Raposo", "Renato Nóbrega", "Rogério Melo",
    "Henrique Bouwman", "Filipe", "Arthur Furtado",
]
RODADA_INI_PADRAO, RODADA_FIM_PADRAO = 20, 38
CONFRONTOS_PADRAO = {
    20: [("Rafael Raposo", "Renato Nóbrega"), ("Rogério Melo", "Henrique Bouwman"), ("Filipe", "Arthur Furtado")],
    21: [("Rafael Raposo", "Henrique Bouwman"), ("Renato Nóbrega", "Arthur Furtado"), ("Rogério Melo", "Filipe")],
    22: [("Rafael Raposo", "Arthur Furtado"), ("Henrique Bouwman", "Filipe"), ("Renato Nóbrega", "Rogério Melo")],
    23: [("Rafael Raposo", "Filipe"), ("Arthur Furtado", "Rogério Melo"), ("Henrique Bouwman", "Renato Nóbrega")],
    24: [("Rafael Raposo", "Rogério Melo"), ("Filipe", "Renato Nóbrega"), ("Arthur Furtado", "Henrique Bouwman")],
    25: [("Renato Nóbrega", "Rafael Raposo"), ("Henrique Bouwman", "Rogério Melo"), ("Arthur Furtado", "Filipe")],
    26: [("Henrique Bouwman", "Rafael Raposo"), ("Arthur Furtado", "Renato Nóbrega"), ("Filipe", "Rogério Melo")],
    27: [("Arthur Furtado", "Rafael Raposo"), ("Filipe", "Henrique Bouwman"), ("Rogério Melo", "Renato Nóbrega")],
    28: [("Filipe", "Rafael Raposo"), ("Rogério Melo", "Arthur Furtado"), ("Renato Nóbrega", "Henrique Bouwman")],
    29: [("Rogério Melo", "Rafael Raposo"), ("Renato Nóbrega", "Filipe"), ("Henrique Bouwman", "Arthur Furtado")],
    30: [("Rafael Raposo", "Renato Nóbrega"), ("Rogério Melo", "Henrique Bouwman"), ("Filipe", "Arthur Furtado")],
    31: [("Rafael Raposo", "Henrique Bouwman"), ("Renato Nóbrega", "Arthur Furtado"), ("Rogério Melo", "Filipe")],
    32: [("Rafael Raposo", "Arthur Furtado"), ("Henrique Bouwman", "Filipe"), ("Renato Nóbrega", "Rogério Melo")],
    33: [("Rafael Raposo", "Filipe"), ("Arthur Furtado", "Rogério Melo"), ("Henrique Bouwman", "Renato Nóbrega")],
    34: [("Rafael Raposo", "Rogério Melo"), ("Filipe", "Renato Nóbrega"), ("Arthur Furtado", "Henrique Bouwman")],
    35: [("Renato Nóbrega", "Rafael Raposo"), ("Henrique Bouwman", "Rogério Melo"), ("Arthur Furtado", "Filipe")],
    36: [("Henrique Bouwman", "Rafael Raposo"), ("Arthur Furtado", "Renato Nóbrega"), ("Filipe", "Rogério Melo")],
    37: [("Arthur Furtado", "Rafael Raposo"), ("Filipe", "Henrique Bouwman"), ("Rogério Melo", "Renato Nóbrega")],
    38: [("Filipe", "Rafael Raposo"), ("Rogério Melo", "Arthur Furtado"), ("Renato Nóbrega", "Henrique Bouwman")],
}

POSICOES = {
    1: "GOL",
    2: "LAT",
    3: "ZAG",
    4: "MEI",
    5: "ATA",
}

FORMACOES = {
    "4-3-3": {"GOL": 1, "LAT": 2, "ZAG": 2, "MEI": 3, "ATA": 3},
    "4-4-2": {"GOL": 1, "LAT": 2, "ZAG": 2, "MEI": 4, "ATA": 2},
    "3-5-2": {"GOL": 1, "ZAG": 3, "MEI": 5, "ATA": 2},
    "3-4-3": {"GOL": 1, "ZAG": 3, "MEI": 4, "ATA": 3},
    "5-3-2": {"GOL": 1, "LAT": 2, "ZAG": 3, "MEI": 3, "ATA": 2},
    "5-4-1": {"GOL": 1, "LAT": 2, "ZAG": 3, "MEI": 4, "ATA": 1},
}

ORDEM_POSICAO = {"GOL": 1, "LAT": 2, "ZAG": 3, "MEI": 4, "ATA": 5}

CSS = """
<style>
  .block-container { padding-top: 1.5rem; max-width: 1400px; }
  .live-top {
      display: inline-flex; align-items: center; gap: 6px;
      color: #00ff87; font-size: 11px; font-weight: 700; letter-spacing: 1.2px;
      vertical-align: middle; margin-left: 4px;
  }
  .live-top .dot, .cc-live .dot {
      width: 8px; height: 8px; border-radius: 50%; background: #00ff87;
      box-shadow: 0 0 7px #00ff87; animation: pulse 1.4s ease-in-out infinite;
  }
  @keyframes pulse { 0%{opacity:1} 50%{opacity:.25} 100%{opacity:1} }
  /* Card do confronto */
  .cc {
      background: #161b22; border: 1px solid #20262e; border-radius: 14px;
      padding: 13px 16px 8px 16px; margin-bottom: 16px;
      box-shadow: 0 6px 18px rgba(0,0,0,0.35);
  }
  .cc-h {
      display: flex; align-items: center; justify-content: space-between;
      color: #7d8896; font-size: 11px; font-weight: 700; letter-spacing: 1.5px;
      text-transform: uppercase; margin-bottom: 10px;
  }
  .cc-h .ttl { display: flex; align-items: center; gap: 7px; }
  .cc-h .ttl::before { content: "\\26BD"; font-size: 13px; }
  .cc-live { display: inline-flex; align-items: center; gap: 5px; color: #00ff87; font-size: 9px; }
  /* Barra de comparacao de placar */
  .cc-bar {
      display: flex; height: 7px; border-radius: 5px; overflow: hidden;
      background: #0d1117; margin-bottom: 12px;
  }
  .cc-bar span { display: block; height: 100%; transition: width .4s; }
  .seg-win { background: #00ff87; box-shadow: 0 0 8px rgba(0,255,135,.5); }
  .seg-lose { background: #39414c; }
  .cc-body { display: grid; grid-template-columns: 1fr 1px 1fr; gap: 14px; }
  .cc-div { background: #20262e; }
  /* Time */
  .tm-top {
      display: flex; align-items: baseline; justify-content: space-between;
      gap: 8px; padding-bottom: 5px; margin-bottom: 6px;
      border-bottom: 1px solid #20262e;
  }
  .tm-id { min-width: 0; }
  .tm-name {
      font-size: 14px; font-weight: 700; color: #e6edf3;
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .tm-sub { font-size: 9px; color: #6e7681; font-weight: 600; letter-spacing: .4px; margin-top: 1px; }
  .tm-score { font-size: 25px; font-weight: 800; color: #9aa4b1; font-variant-numeric: tabular-nums; line-height: 1; }
  .tm.win .tm-name { color: #00ff87; }
  .tm.win .tm-score { color: #00ff87; text-shadow: 0 0 10px rgba(0,255,135,0.45); }
  .crown { font-size: 11px; margin-left: 4px; }
  /* Lineup */
  table.lu { width: 100%; border-collapse: collapse; font-size: 12px; }
  table.lu td { padding: 2px 3px; color: #c9d1d9; border: 0; }
  table.lu tr.played { background: rgba(0,255,135,0.06); }
  td.pos {
      width: 32px; text-align: center;
  }
  td.pos span {
      display: inline-block; background: #21262d; color: #8b949e;
      font-size: 9px; font-weight: 700; letter-spacing: .5px;
      padding: 1px 5px; border-radius: 4px;
  }
  td.nm { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 115px; }
  td.nm img { width: 15px; height: 15px; border-radius: 2px; vertical-align: -2px; margin-right: 5px; }
  .sdot { display: inline-block; width: 7px; height: 7px; border-radius: 50%;
          margin-right: 6px; vertical-align: 1px; }
  .sdot.dg { background: #00ff87; box-shadow: 0 0 5px rgba(0,255,135,0.7); }
  .sdot.dr { background: #f0746b; box-shadow: 0 0 5px rgba(240,116,107,0.7); }
  .sdot.dn { background: #3a4150; }
  .sdot.blink { animation: pulse 1.4s ease-in-out infinite; }
  .star { color: #f5c518; margin-left: 3px; font-size: 10px; }
  td.pt { text-align: right; font-variant-numeric: tabular-nums; font-weight: 600; width: 46px; }
  td.pt.pos-val { color: #3fd07f; }
  td.pt.neg-val { color: #f0746b; }
  .empty { color: #6e7681; font-size: 12px; font-style: italic; padding: 6px 2px; }
  /* Botao "Habilitar edicao" (key=btn_habilitar) */
  section[data-testid="stSidebar"] .st-key-btn_habilitar button {
      background: linear-gradient(180deg, #00ff87 0%, #00d873 100%);
      color: #06210f; font-weight: 800; letter-spacing: .3px;
      border: 0; border-radius: 10px; padding: 11px 14px;
      box-shadow: 0 4px 14px rgba(0,255,135,.30);
      transition: transform .15s ease, box-shadow .15s ease;
  }
  section[data-testid="stSidebar"] .st-key-btn_habilitar button:hover {
      box-shadow: 0 6px 20px rgba(0,255,135,.48);
      transform: translateY(-1px);
  }
  section[data-testid="stSidebar"] .st-key-btn_habilitar button:active { transform: translateY(0); }
  /* Base coerente para todos os botoes da sidebar */
  section[data-testid="stSidebar"] .stButton button {
      border-radius: 10px; font-weight: 700; letter-spacing: .2px;
      padding: 10px 14px; border: 1px solid #30363d;
      transition: transform .15s ease, box-shadow .15s ease,
                  background .15s ease, border-color .15s ease;
  }
  section[data-testid="stSidebar"] .stButton button:hover { transform: translateY(-1px); }
  section[data-testid="stSidebar"] .stButton button:active { transform: translateY(0); }
  /* Neutro: Atualizar parciais / Bloquear edicao / Arquivar rodada */
  section[data-testid="stSidebar"] .st-key-btn_atualizar button,
  section[data-testid="stSidebar"] .st-key-btn_arquivar button,
  section[data-testid="stSidebar"] .st-key-btn_bloquear button {
      background: #1b2027; color: #c9d1d9; border-color: #30363d;
  }
  section[data-testid="stSidebar"] .st-key-btn_atualizar button:hover,
  section[data-testid="stSidebar"] .st-key-btn_bloquear button:hover {
      background: #222a33; border-color: #3d444d;
  }
  /* Perigo: Limpar tudo (sidebar) e confirmar exclusao (dialogo) */
  section[data-testid="stSidebar"] .st-key-btn_limpar button,
  .st-key-btn_confirma_limpar button {
      background: rgba(240,116,107,.12); color: #f0746b;
      border: 1px solid rgba(240,116,107,.40); font-weight: 700; border-radius: 10px;
  }
  section[data-testid="stSidebar"] .st-key-btn_limpar button:hover,
  .st-key-btn_confirma_limpar button:hover {
      background: rgba(240,116,107,.20);
      box-shadow: 0 4px 14px rgba(240,116,107,.28);
  }
  /* Banner de edicao bloqueada */
  .edit-locked {
      display: flex; align-items: center; gap: 14px;
      background: linear-gradient(90deg, rgba(240,116,107,.12), rgba(240,116,107,0) 90%);
      border: 1px solid rgba(240,116,107,.30);
      border-left: 4px solid #f0746b;
      border-radius: 10px; padding: 14px 18px; margin: 2px 0 18px;
  }
  .edit-locked .ico { font-size: 22px; line-height: 1; }
  .edit-locked .txt { color: #e6edf3; font-weight: 700; font-size: 14px; }
  .edit-locked .sub { color: #9aa4b1; font-weight: 400; font-size: 12px; margin-top: 2px; }
  /* Titulo de secao (coerente com o cabecalho dos cards) */
  .sec-title {
      font-size: 12px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase;
      color: #7d8896; margin: 18px 0 12px; padding-left: 10px;
      border-left: 3px solid #00ff87;
  }
  /* Cabecalho da sidebar coerente */
  section[data-testid="stSidebar"] h2 { font-size: 15px; letter-spacing: .3px; }
</style>
"""


# ---------------------------------------------------------------------------
# Acesso a dados
# ---------------------------------------------------------------------------
def requisicao_json(url: str) -> Optional[Dict]:
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Erro ao acessar a API: {exc}")
        return None
    # Corpo vazio/não-JSON é normal quando o mercado está aberto (sem parciais):
    # retorna None silenciosamente e deixa o app mostrar o aviso amigável.
    try:
        return response.json()
    except ValueError:
        return None


@st.cache_data(ttl=60)
def carregar_parciais() -> Optional[Dict]:
    return requisicao_json(f"{API_BASE}/atletas/pontuados")


@st.cache_data(ttl=60)
def carregar_mercado() -> Optional[Dict]:
    return requisicao_json(f"{API_BASE}/atletas/mercado")


@st.cache_data(ttl=60)
def carregar_partidas() -> Optional[Dict]:
    return requisicao_json(f"{API_BASE}{PARTIDAS_PATH}")


@st.cache_data(ttl=60)
def carregar_mercado_status() -> Optional[Dict]:
    return requisicao_json(f"{API_BASE}/mercado/status")


def carregar_pesos_scouts() -> Dict[str, float]:
    """Pesos da liga (scouts_pontuacao.json) usados na pontuação parcial."""
    if not os.path.exists(SCOUTS_PESOS_FILE):
        st.error(f"Arquivo {SCOUTS_PESOS_FILE} não encontrado.")
        return {}
    try:
        with open(SCOUTS_PESOS_FILE, "r", encoding="utf-8") as f:
            return {str(k): float(v) for k, v in json.load(f).items()}
    except Exception as exc:  # noqa: BLE001
        st.error(f"Erro ao carregar {SCOUTS_PESOS_FILE}: {exc}")
        return {}


def pontuacao_scouts(scout: Optional[Dict], pesos: Dict[str, float]) -> float:
    if not scout:
        return 0.0
    return sum(float(qtd) * pesos.get(chave, 0.0) for chave, qtd in scout.items())


def coletar_clubes(*fontes: Optional[Dict]) -> Dict[int, Dict]:
    """Une os clubes (selecoes) das varias fontes da API, com seus escudos."""
    clubes: Dict[int, Dict] = {}
    for fonte in fontes:
        if not isinstance(fonte, dict):
            continue
        for cid, info in (fonte.get("clubes", {}) or {}).items():
            if not isinstance(info, dict):
                continue
            try:
                clubes.setdefault(int(cid), info)
            except (TypeError, ValueError):
                continue
    return clubes


def partida_status(p: Dict) -> str:
    """Heuristica: 'ao_vivo', 'encerrado' ou 'nao_iniciado'."""
    if not isinstance(p, dict):
        return "nao_iniciado"
    for bkey in ("em_andamento", "ao_vivo", "live"):
        if isinstance(p.get(bkey), bool) and p.get(bkey):
            return "ao_vivo"
    textos = []
    for k in (
        "status_transmissao_tr", "periodo_tr", "status_cronometro_tr",
        "status", "periodo", "transmissao", "fase",
    ):
        v = p.get(k)
        if isinstance(v, str):
            textos.append(v.lower())
    blob = " ".join(textos)
    encerrado = ["encerr", "fim", "final", "pos-jogo", "pos jogo", "terminad"]
    ao_vivo = [
        "andamento", "ao vivo", "ao_vivo", " vivo", "intervalo",
        "1º", "2º", "1o ", "2o ", "prorrog", "penal", "em curso", "live", "tempo",
    ]
    if any(x in blob for x in encerrado):
        return "encerrado"
    if any(x in blob for x in ao_vivo):
        return "ao_vivo"
    return "nao_iniciado"


def mapa_status_jogos(partidas: Optional[Dict]) -> Dict[int, str]:
    """Mapeia clube_id -> status do jogo ('ao_vivo'/'encerrado'/'nao_iniciado')."""
    status: Dict[int, str] = {}
    if not isinstance(partidas, dict):
        return status
    lista = partidas.get("partidas") or partidas.get("jogos") or []
    if not isinstance(lista, list):
        return status
    for p in lista:
        if not isinstance(p, dict):
            continue
        st_jogo = partida_status(p)
        for ckey in ("clube_casa_id", "clube_visitante_id", "mandante_id", "visitante_id"):
            cid = p.get(ckey)
            if cid is None:
                continue
            try:
                status[int(cid)] = st_jogo
            except (TypeError, ValueError):
                continue
    return status


# ---------------------------------------------------------------------------
# Persistencia da escalacao (Google Sheets com fallback em arquivo local)
# ---------------------------------------------------------------------------
def _gsheets_configurado() -> bool:
    """True se os secrets do Google Sheets estiverem presentes."""
    try:
        return "gcp_service_account" in st.secrets and "gsheets" in st.secrets
    except Exception:  # noqa: BLE001
        return False


@st.cache_resource(show_spinner=False)
def _worksheet_estado():
    """Abre (ou cria) a worksheet onde o estado e guardado como JSON em A1."""
    import gspread

    gc = gspread.service_account_from_dict(dict(st.secrets["gcp_service_account"]))
    conf = st.secrets["gsheets"]
    if conf.get("spreadsheet_key"):
        sh = gc.open_by_key(conf["spreadsheet_key"])
    elif conf.get("spreadsheet_url"):
        sh = gc.open_by_url(conf["spreadsheet_url"])
    else:
        sh = gc.open(conf.get("spreadsheet", "Cartola Copa Escalacoes"))
    nome = conf.get("worksheet", "estado")
    try:
        return sh.worksheet(nome)
    except Exception:  # noqa: BLE001
        return sh.add_worksheet(title=nome, rows=2, cols=2)


@st.cache_resource(show_spinner=False)
def _planilha():
    """Abre a planilha (para criar/atualizar as abas rodada{N})."""
    import gspread

    gc = gspread.service_account_from_dict(dict(st.secrets["gcp_service_account"]))
    conf = st.secrets["gsheets"]
    if conf.get("spreadsheet_key"):
        return gc.open_by_key(conf["spreadsheet_key"])
    if conf.get("spreadsheet_url"):
        return gc.open_by_url(conf["spreadsheet_url"])
    return gc.open(conf.get("spreadsheet", "Cartola Copa Escalacoes"))


def montar_linhas_rodada(rodada, confrontos, parciais, atletas_por_id, clubes_por_id, pesos):
    """Linhas [Participante, Jogador, Posição, Clube, Parcial] + total por time."""
    from datetime import datetime, timezone

    parciais_atletas = (parciais or {}).get("atletas", {}) or {}
    quando = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    linhas = [[f"Rodada {rodada} — arquivado em {quando}"],
              ["Participante", "Jogador", "Posição", "Clube", "Parcial"]]
    for n in sorted(confrontos, key=lambda x: int(x)):
        conf = confrontos[n] or {}
        for lado in ("a", "b"):
            time = conf.get(lado, {}) or {}
            participante = (time.get("nome") or f"Confronto {n} - {lado.upper()}").strip()
            selecao = time.get("selecao", {}) or {}
            total = 0.0
            tem = False
            for _slot, aid in selecao.items():
                if not aid:
                    continue
                tem = True
                meta = atletas_por_id.get(aid, {})
                info = parciais_atletas.get(str(aid)) or parciais_atletas.get(aid) or {}
                scout = info.get("scout", {}) if isinstance(info, dict) else {}
                pts = round(pontuacao_scouts(scout, pesos), 2)
                total += pts
                clube = clubes_por_id.get(meta.get("clube_id"), {}) if meta.get("clube_id") else {}
                linhas.append([participante, meta.get("apelido", str(aid)),
                               POSICOES.get(meta.get("posicao_id"), ""),
                               (clube or {}).get("abreviacao", ""), pts])
            if tem:
                linhas.append([participante, "TOTAL", "", "", round(total, 2)])
        linhas.append([])
    return linhas


def arquivar_rodada_no_sheets(rodada, linhas):
    """Cria/sobrescreve a aba rodada{N} com as linhas. Retorna o nome da aba."""
    sh = _planilha()
    aba = f"rodada{rodada}"
    if aba in [w.title for w in sh.worksheets()]:
        ws = sh.worksheet(aba)
        ws.clear()
    else:
        ws = sh.add_worksheet(title=aba, rows=len(linhas) + 10, cols=6)
    ws.update(values=linhas, range_name="A1")
    return aba


def _rodadas_disponiveis(sh) -> List[int]:
    """Números das rodadas com aba `rodada{N}` na planilha, ordenados."""
    nums = []
    for w in sh.worksheets():
        m = re.fullmatch(r"rodada(\d+)", (w.title or "").strip())
        if m:
            nums.append(int(m.group(1)))
    return sorted(nums)


def _ler_rodada(sh, rodada) -> List[List[str]]:
    return sh.worksheet(f"rodada{rodada}").get_all_values()


def _totais_confrontos(valores) -> List[Tuple[str, float, str, float]]:
    """Extrai (time_a, pts_a, time_b, pts_b) das linhas TOTAL, em pares (A, B)."""
    totais: List[Tuple[str, float]] = []
    for row in valores:
        if len(row) >= 5 and str(row[1]).strip().upper() == "TOTAL":
            try:
                pts = float(str(row[4]).replace(",", "."))
            except (TypeError, ValueError):
                pts = 0.0
            totais.append((str(row[0]).strip(), pts))
    confrontos = []
    for i in range(0, len(totais) - 1, 2):
        (a, pa), (b, pb) = totais[i], totais[i + 1]
        confrontos.append((a, pa, b, pb))
    return confrontos


def calcular_classificacao(sh, rodada_ini=None, rodada_fim=None):
    """Agrega os confrontos das rodadas arquivadas dentro do range. Retorna (linhas, rodadas)."""
    from collections import defaultdict

    stats = defaultdict(lambda: {"J": 0, "V": 0, "E": 0, "D": 0, "PF": 0.0, "PS": 0.0})
    rodadas = [
        r for r in _rodadas_disponiveis(sh)
        if (rodada_ini is None or r >= rodada_ini) and (rodada_fim is None or r <= rodada_fim)
    ]
    for r in rodadas:
        try:
            confrontos = _totais_confrontos(_ler_rodada(sh, r))
        except Exception:  # noqa: BLE001
            continue
        for a, pa, b, pb in confrontos:
            for me, mine, theirs in ((a, pa, pb), (b, pb, pa)):
                if not me:
                    continue
                s = stats[me]
                s["J"] += 1
                s["PF"] += mine
                s["PS"] += theirs
                if mine > theirs:
                    s["V"] += 1
                elif mine == theirs:
                    s["E"] += 1
                else:
                    s["D"] += 1
    linhas = [
        {"Participante": nome, "J": s["J"], "V": s["V"], "E": s["E"], "D": s["D"],
         "Pontos feitos": round(s["PF"], 2), "Pontos sofridos": round(s["PS"], 2)}
        for nome, s in stats.items()
    ]
    # Critérios: vitórias > empates > pontos feitos > menos pontos sofridos.
    linhas.sort(key=lambda x: (x["V"], x["E"], x["Pontos feitos"], -x["Pontos sofridos"]), reverse=True)
    return linhas, rodadas


def _mostrar_tabela_rodada(valores) -> None:
    """Renderiza a aba rodada{N} (matriz de valores) como tabela."""
    if not valores:
        st.info("Aba vazia.")
        return
    titulo = valores[0][0] if valores[0] else ""
    if titulo:
        st.caption(titulo)
    header = valores[1] if len(valores) > 1 else []
    dados = [r for r in valores[2:] if any(str(c).strip() for c in r)]
    if header and dados:
        ncol = len(header)
        dados = [(list(r) + [""] * ncol)[:ncol] for r in dados]
        st.dataframe(pd.DataFrame(dados, columns=header), width="stretch", hide_index=True)
    else:
        st.info("Sem dados nesta rodada.")


def _garantir_config(sh) -> None:
    """Cria as abas `participantes`, `confrontos` e `config` com os padrões, se faltarem."""
    titulos = [w.title for w in sh.worksheets()]
    if "participantes" not in titulos:
        ws = sh.add_worksheet(title="participantes", rows=8, cols=4)
        linhas = [["Posição", "Nome", "Apelido", "Senha"]]
        for i, nome in enumerate(PARTICIPANTES_PADRAO, start=1):
            linhas.append([i, nome, nome, ""])
        ws.update(values=linhas, range_name="A1")
    if "confrontos" not in titulos:
        ws = sh.add_worksheet(title="confrontos", rows=len(CONFRONTOS_PADRAO) + 2, cols=7)
        linhas = [["Rodada", "Casa 1", "Fora 1", "Casa 2", "Fora 2", "Casa 3", "Fora 3"]]
        for r in sorted(CONFRONTOS_PADRAO):
            linha = [r]
            for a, b in CONFRONTOS_PADRAO[r]:
                linha += [a, b]
            linhas.append(linha)
        ws.update(values=linhas, range_name="A1")
    if "config" not in titulos:
        ws = sh.add_worksheet(title="config", rows=6, cols=2)
        ws.update(values=[
            ["rodada_inicial", RODADA_INI_PADRAO],
            ["rodada_final", RODADA_FIM_PADRAO],
            ["senha_master", ""],
        ], range_name="A1")


@st.cache_data(ttl=120, show_spinner=False)
def carregar_config() -> Dict:
    """Lê a config (participantes, senhas, range, confrontos) da planilha; padrões se falhar."""
    cfg = {
        "participantes": list(PARTICIPANTES_PADRAO),
        "apelidos": list(PARTICIPANTES_PADRAO),
        "senhas": ["" for _ in PARTICIPANTES_PADRAO],
        "senha_master": "",
        "rodada_ini": RODADA_INI_PADRAO,
        "rodada_fim": RODADA_FIM_PADRAO,
        "confrontos": {r: list(v) for r, v in CONFRONTOS_PADRAO.items()},
    }
    if not _gsheets_configurado():
        return cfg
    try:
        sh = _planilha()
        _garantir_config(sh)

        nomes, apelidos, senhas = [], [], []
        for row in sh.worksheet("participantes").get_all_values()[1:]:
            if len(row) >= 2 and str(row[1]).strip():
                nome = str(row[1]).strip()
                nomes.append(nome)
                apelidos.append(str(row[2]).strip() if len(row) >= 3 and str(row[2]).strip() else nome)
                senhas.append(str(row[3]).strip() if len(row) >= 4 else "")
        if nomes:
            cfg["participantes"] = nomes
            cfg["apelidos"] = apelidos
            cfg["senhas"] = senhas

        for row in sh.worksheet("config").get_all_values():
            if not row:
                continue
            chave = str(row[0]).strip().lower()
            valor = str(row[1]).strip() if len(row) > 1 else ""
            if chave == "rodada_inicial" and valor.isdigit():
                cfg["rodada_ini"] = int(valor)
            elif chave == "rodada_final" and valor.isdigit():
                cfg["rodada_fim"] = int(valor)
            elif chave == "senha_master":
                cfg["senha_master"] = valor

        conf = {}
        for row in sh.worksheet("confrontos").get_all_values()[1:]:
            if not row or not str(row[0]).strip().isdigit():
                continue
            cells = [str(c).strip() for c in row[1:]]
            pares = [(cells[i], cells[i + 1]) for i in range(0, 6, 2)
                     if i + 1 < len(cells) and cells[i] and cells[i + 1]]
            if pares:
                conf[int(str(row[0]).strip())] = pares
        if conf:
            cfg["confrontos"] = conf
    except Exception:  # noqa: BLE001
        pass
    return cfg


# --------------------------------------------------------- utilitários (admin/teste)
def resetar_config_tabs(sh) -> None:
    """Apaga e recria as abas participantes/confrontos/config no formato padrão."""
    for w in list(sh.worksheets()):
        if w.title in ("participantes", "confrontos", "config"):
            sh.del_worksheet(w)
    _garantir_config(sh)


def gerar_rodadas_fake(sh, cfg, rodadas) -> List[int]:
    """Cria abas rodada{N} FICTÍCIAS (marcadas [TESTE]) para as rodadas dadas."""
    import random

    nome2ap = {n: a for n, a in zip(cfg["participantes"], cfg["apelidos"])}
    feitas = []
    for r in rodadas:
        pares = cfg["confrontos"].get(r)
        if not pares:
            continue
        linhas = [[f"Rodada {r} — [TESTE] dados fictícios"],
                  ["Participante", "Jogador", "Posição", "Clube", "Parcial"]]
        for a, b in pares:
            for nome in (a, b):
                linhas.append([nome2ap.get(nome, nome), "TOTAL", "", "", round(random.uniform(20, 90), 2)])
            linhas.append([])
        aba = f"rodada{r}"
        if aba in [w.title for w in sh.worksheets()]:
            ws = sh.worksheet(aba)
            ws.clear()
        else:
            ws = sh.add_worksheet(title=aba, rows=len(linhas) + 5, cols=6)
        ws.update(values=linhas, range_name="A1")
        feitas.append(r)
    return feitas


def apagar_rodadas_teste(sh) -> List[str]:
    """Apaga apenas as abas rodada{N} marcadas com [TESTE] no topo."""
    apagadas = []
    for w in list(sh.worksheets()):
        if not re.fullmatch(r"rodada\d+", (w.title or "").strip()):
            continue
        try:
            a1 = (w.acell("A1").value or "").upper()
        except Exception:  # noqa: BLE001
            a1 = ""
        if "TESTE" in a1:
            sh.del_worksheet(w)
            apagadas.append(w.title)
    return apagadas


def carregar_estado() -> Tuple[Dict, bool]:
    """Le o estado salvo. Retorna (dados, leitura_ok).

    leitura_ok=False sinaliza FALHA de leitura (ex.: Sheets fora do ar). Nesse
    caso o app NAO deve salvar, para nao sobrescrever os dados bons com vazio.
    """
    if _gsheets_configurado():
        try:
            raw = _worksheet_estado().acell("A1").value
            return (json.loads(raw) if raw else {}), True
        except Exception as exc:  # noqa: BLE001
            st.error(f"Falha ao ler do Google Sheets ({exc}). Edição desativada nesta sessão para proteger os dados.")
            return {}, False
    # Fallback local
    if not os.path.exists(ESCALACAO_FILE):
        return {}, True
    try:
        with open(ESCALACAO_FILE, "r", encoding="utf-8") as f:
            return (json.load(f) or {}), True
    except Exception:  # noqa: BLE001
        return {}, False


def salvar_escalacao_salva(dados: Dict) -> None:
    if _gsheets_configurado():
        try:
            _worksheet_estado().update_acell("A1", json.dumps(dados, ensure_ascii=False))
            return
        except Exception as exc:  # noqa: BLE001
            st.warning(f"Falha ao salvar no Google Sheets ({exc}). Salvando localmente.")
    try:
        with open(ESCALACAO_FILE, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Erro ao salvar {ESCALACAO_FILE}: {exc}")


def limpar_escalacao_salva() -> None:
    if _gsheets_configurado():
        try:
            _worksheet_estado().update_acell("A1", "")
        except Exception as exc:  # noqa: BLE001
            st.warning(f"Falha ao limpar no Google Sheets ({exc}).")
    try:
        if os.path.exists(ESCALACAO_FILE):
            os.remove(ESCALACAO_FILE)
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Não foi possível remover {ESCALACAO_FILE}: {exc}")

    for key in list(st.session_state.keys()):
        if (
            key.startswith("c")
            or key.startswith("nome_")
            or key.startswith("formacao_")
            or key in (
                "num_confrontos", "_ultimo_salvo",
                "_base_conf", "_base_num", "dados_salvos",
            )
        ):
            del st.session_state[key]
    st.session_state["escalacao_carregada"] = False


# ---------------------------------------------------------------------------
# Helpers de formacao / selecao
# ---------------------------------------------------------------------------
def listar_slots_com_indices(formacao: Dict[str, int]) -> List[Tuple[str, int]]:
    slots: List[Tuple[str, int]] = []
    for posicao in ["GOL", "LAT", "ZAG", "MEI", "ATA"]:
        for idx in range(1, formacao.get(posicao, 0) + 1):
            slots.append((posicao, idx))
    return slots


def opcoes_por_posicao(
    atletas: List[Dict],
    clubes_por_id: Dict[int, Dict],
) -> Tuple[Dict[str, List[int]], Dict[int, str]]:
    opcoes: Dict[str, List[int]] = {pos: [] for pos in POSICOES.values()}
    id_para_label: Dict[int, str] = {}

    for atleta in atletas:
        posicao = POSICOES.get(atleta.get("posicao_id"))
        if not posicao:
            continue
        atleta_id = atleta.get("atleta_id")
        if atleta_id is None:
            continue
        clube_id = atleta.get("clube_id")
        clube_info = clubes_por_id.get(clube_id, {}) if clube_id is not None else {}
        clube_abrev = clube_info.get("abreviacao") or clube_info.get("nome") or str(clube_id)
        id_para_label[atleta_id] = f"{atleta.get('apelido', '')} ({clube_abrev})"
        opcoes[posicao].append(atleta_id)

    for pos in opcoes:
        opcoes[pos].sort(key=lambda atleta_id: id_para_label.get(atleta_id, ""))

    return opcoes, id_para_label


def montar_tabela_escalacao(
    escalacao_ids: List[int],
    parciais: Dict,
    atletas_por_id: Dict[int, Dict],
    clubes_por_id: Dict[int, Dict],
    pesos: Dict[str, float],
    status_jogos: Optional[Dict[int, str]] = None,
) -> pd.DataFrame:
    parciais_atletas = parciais.get("atletas", {}) if parciais else {}
    linhas: List[Dict] = []

    for atleta_id in escalacao_ids:
        atleta = atletas_por_id.get(atleta_id, {})
        parcial_info = parciais_atletas.get(str(atleta_id), {}) or parciais_atletas.get(
            atleta_id, {}
        )
        scout = parcial_info.get("scout", {}) if isinstance(parcial_info, dict) else {}
        pontuacao = pontuacao_scouts(scout, pesos)
        entrou_em_campo = (
            parcial_info.get("entrou_em_campo")
            if isinstance(parcial_info, dict)
            else False
        )
        clube_id = atleta.get("clube_id")
        clube_info = clubes_por_id.get(clube_id, {}) if clube_id is not None else {}
        escudos = clube_info.get("escudos", {}) if isinstance(clube_info, dict) else {}
        clube_escudo = escudos.get("30x30") or escudos.get("45x45") or escudos.get("60x60") or ""

        linhas.append(
            {
                "Jogador": atleta.get("apelido", "N/A"),
                "Posicao": POSICOES.get(atleta.get("posicao_id"), "N/A"),
                "Clube": clube_escudo,
                "Jogou": bool(entrou_em_campo),
                "JogoStatus": (status_jogos or {}).get(clube_id, "nao_iniciado"),
                "Parcial": pontuacao,
            }
        )

    df = pd.DataFrame(linhas)
    if not df.empty:
        df["__ordem"] = df["Posicao"].map(ORDEM_POSICAO).fillna(99)
        df = df.sort_values(by=["__ordem", "Parcial"], ascending=[True, False])
        df = df.drop(columns=["__ordem"])
    return df


def total_time(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    return float(df["Parcial"].sum())


def jogadores_em_campo(df: pd.DataFrame) -> int:
    if df.empty or "Jogou" not in df:
        return 0
    return int(df["Jogou"].sum())


# ---------------------------------------------------------------------------
# Render dos cards (tema escuro refinado)
# ---------------------------------------------------------------------------
def html_lineup(df: pd.DataFrame, top_val: Optional[float]) -> str:
    if df.empty:
        return "<div class='empty'>Sem jogadores selecionados.</div>"
    rows = []
    for _, r in df.iterrows():
        jogou = bool(r.get("Jogou"))
        played = "played" if jogou else ""
        pos = escape(str(r.get("Posicao", "")))
        nome = escape(str(r.get("Jogador", "")))
        val = float(r.get("Parcial", 0))
        cls = "pos-val" if val > 0 else ("neg-val" if val < 0 else "")
        escudo = r.get("Clube", "")
        img = f"<img src='{escape(str(escudo))}'>" if escudo else ""
        st_jogo = str(r.get("JogoStatus") or "nao_iniciado")
        if jogou:
            cor = "dg"
        elif st_jogo == "nao_iniciado":
            cor = "dn"
        else:
            cor = "dr"
        blink = " blink" if (st_jogo == "ao_vivo" and cor != "dn") else ""
        dot = f"<span class='sdot {cor}{blink}'></span>"
        star = (
            "<span class='star'>&#9733;</span>"
            if (top_val is not None and val == top_val and val > 0)
            else ""
        )
        rows.append(
            f"<tr class='{played}'>"
            f"<td class='pos'><span>{pos}</span></td>"
            f"<td class='nm'>{dot}{img}{nome}{star}</td>"
            f"<td class='pt {cls}'>{val:.2f}</td>"
            f"</tr>"
        )
    return "<table class='lu'>" + "".join(rows) + "</table>"


def html_time(nome, df, total, vencedor, top_val) -> str:
    win = "win" if vencedor else ""
    crown = "<span class='crown'>&#128081;</span>" if vencedor else ""
    em_campo = jogadores_em_campo(df)
    tot_sel = 0 if df.empty else len(df)
    sub = f"{em_campo}/{tot_sel} em campo" if tot_sel else "sem escalação"
    return (
        f"<div class='tm {win}'>"
        f"<div class='tm-top'>"
        f"<div class='tm-id'>"
        f"<div class='tm-name'>{escape(nome)}{crown}</div>"
        f"<div class='tm-sub'>{sub}</div>"
        f"</div>"
        f"<span class='tm-score'>{total:.2f}</span>"
        f"</div>{html_lineup(df, top_val)}</div>"
    )


def barra_placar(tot_a: float, tot_b: float) -> Tuple[float, float]:
    """Retorna (largura_a, largura_b) em % para a barra de comparacao."""
    pa, pb = max(tot_a, 0.0), max(tot_b, 0.0)
    base = pa + pb
    if base <= 0:
        return 50.0, 50.0
    wa = pa / base * 100.0
    return wa, 100.0 - wa


def html_confronto(n, nome_a, df_a, tot_a, nome_b, df_b, tot_b) -> str:
    a_win = tot_a > tot_b
    b_win = tot_b > tot_a
    top_val = None
    vals = [
        v
        for d in (df_a, df_b)
        if not d.empty
        for v in d["Parcial"].tolist()
    ]
    if vals and max(vals) > 0:
        top_val = max(vals)
    wa, wb = barra_placar(tot_a, tot_b)
    seg_a = "seg-win" if a_win or (not b_win) else "seg-lose"
    seg_b = "seg-win" if b_win else "seg-lose"
    if a_win:
        seg_a, seg_b = "seg-win", "seg-lose"
    elif b_win:
        seg_a, seg_b = "seg-lose", "seg-win"
    else:
        seg_a = seg_b = "seg-lose"
    return (
        f"<div class='cc'>"
        f"<div class='cc-h'><span class='ttl'>Confronto {n}</span></div>"
        f"<div class='cc-bar'>"
        f"<span class='{seg_a}' style='width:{wa:.1f}%'></span>"
        f"<span class='{seg_b}' style='width:{wb:.1f}%'></span>"
        f"</div>"
        f"<div class='cc-body'>"
        f"{html_time(nome_a, df_a, tot_a, a_win, top_val)}"
        f"<div class='cc-div'></div>"
        f"{html_time(nome_b, df_b, tot_b, b_win, top_val)}"
        f"</div></div>"
    )


# ---------------------------------------------------------------------------
# Editor de um time (dentro do expander)
# ---------------------------------------------------------------------------
def render_editor_time(
    prefixo: str,
    titulo_padrao: str,
    formacao_padrao: str,
    salvo: Dict,
    opcoes: Dict[str, List[int]],
    id_para_label: Dict[int, str],
) -> Tuple[str, str, Dict[str, Optional[int]], List[int]]:
    nome_key = f"nome_{prefixo}"
    if nome_key not in st.session_state:
        st.session_state[nome_key] = salvo.get("nome") or titulo_padrao
    nome = st.text_input("Nome do time", key=nome_key)

    formacao_key = f"formacao_{prefixo}"
    if formacao_key not in st.session_state:
        salva = salvo.get("formacao")
        st.session_state[formacao_key] = salva if salva in FORMACOES else formacao_padrao
    formacao = st.selectbox("Formação", list(FORMACOES.keys()), key=formacao_key)

    selecao_salva = salvo.get("selecao", {}) or {}
    selecao: Dict[str, Optional[int]] = {}
    ids: List[int] = []

    for pos, idx in listar_slots_com_indices(FORMACOES[formacao]):
        chave_slot = f"{pos}_{idx}"
        state_key = f"{prefixo}_{pos}_{idx}"
        salvo_id = selecao_salva.get(chave_slot)
        opcoes_ids = [0] + opcoes.get(pos, [])
        # Preserva o jogador salvo mesmo que o mercado nao o liste agora
        # (ex.: mercado fechado/API vazia) para nunca zerar a escalacao salva.
        if salvo_id and salvo_id not in opcoes_ids:
            opcoes_ids.append(salvo_id)
        if st.session_state.get(state_key) not in opcoes_ids:
            st.session_state[state_key] = salvo_id if salvo_id in opcoes_ids else 0
        atleta_id = st.selectbox(
            f"{pos} {idx}",
            options=opcoes_ids,
            format_func=lambda x: "-" if x == 0 else id_para_label.get(x, str(x)),
            key=state_key,
        )
        selecao[chave_slot] = atleta_id or None
        if atleta_id:
            ids.append(atleta_id)

    if len(ids) != len(set(ids)):
        st.warning("Jogador repetido nesta escalação.")

    return nome, formacao, selecao, ids


# ---------------------------------------------------------------------------
# Seguranca / autenticacao
# ---------------------------------------------------------------------------
def senha_app() -> Optional[str]:
    """Le a senha de edicao dos secrets ([app].senha ou senha). None = sem protecao."""
    try:
        sec = st.secrets
        if "app" in sec and sec["app"].get("senha"):
            return str(sec["app"]["senha"])
        if "senha" in sec:
            return str(sec["senha"])
    except Exception:  # noqa: BLE001
        pass
    return None


def ids_da_selecao(selecao: Optional[Dict]) -> List[int]:
    if not isinstance(selecao, dict):
        return []
    out: List[int] = []
    for v in selecao.values():
        if v:
            try:
                out.append(int(v))
            except (TypeError, ValueError):
                continue
    return out


def titulo_secao(texto: str) -> None:
    """Renderiza um titulo de secao no mesmo estilo do cabecalho dos cards."""
    st.markdown(f"<div class='sec-title'>{escape(texto)}</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title="Fantasy Draft", page_icon="🏆", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    st.title("🏆 Fantasy Draft")
    st.caption(
        "Liga de fantasy (draft) do Cartola — 6 participantes em 3 confrontos por rodada. "
        "Parciais ao vivo (pontuação pelos pesos da liga), histórico por rodada e classificação do turno. "
        "Atualiza automaticamente a cada 10 minutos."
    )

    # Atualiza as parciais automaticamente a cada 10 minutos (sem recarregar a pagina).
    INTERVALO_REFRESH = 600  # segundos
    if "_ultimo_refresh" not in st.session_state:
        st.session_state["_ultimo_refresh"] = time.time()

    @st.fragment(run_every=30)
    def _auto_refresh():
        if time.time() - st.session_state.get("_ultimo_refresh", 0) >= INTERVALO_REFRESH:
            st.session_state["_ultimo_refresh"] = time.time()
            st.cache_data.clear()
            st.rerun(scope="app")

    _auto_refresh()

    if "escalacao_carregada" not in st.session_state:
        salvos, leitura_ok = carregar_estado()
        st.session_state.dados_salvos = salvos
        st.session_state.leitura_ok = leitura_ok
        if "num_confrontos" not in st.session_state:
            st.session_state.num_confrontos = int(salvos.get("num_confrontos", 1) or 1)
        st.session_state.escalacao_carregada = True

    dados_salvos = st.session_state.get("dados_salvos", {})
    confrontos_salvos = (
        dados_salvos.get("confrontos", {}) if isinstance(dados_salvos, dict) else {}
    )

    senha = senha_app()
    if "autorizado" not in st.session_state:
        st.session_state.autorizado = senha is None  # sem senha = sem protecao
    autorizado = bool(st.session_state.autorizado)

    @st.dialog("Habilitar edição")
    def _dialogo_senha():
        st.write("Digite a senha para liberar a edição dos confrontos.")
        pwd = st.text_input("Senha", type="password", key="dlg_senha")
        col_ok, col_cancel = st.columns(2)
        if col_ok.button("Entrar", type="primary", use_container_width=True):
            if pwd == senha:
                st.session_state.autorizado = True
                st.rerun()
            else:
                st.error("Senha incorreta.")
        if col_cancel.button("Cancelar", use_container_width=True):
            st.rerun()

    @st.dialog("Apagar tudo?")
    def _dialogo_limpar():
        st.warning(
            "Isso vai apagar TODAS as escalações salvas (de todos os confrontos). "
            "Esta ação não pode ser desfeita."
        )
        col_sim, col_nao = st.columns(2)
        if col_sim.button(
            "Sim, apagar tudo",
            use_container_width=True,
            key="btn_confirma_limpar",
        ):
            limpar_escalacao_salva()
            st.session_state["_ultimo_salvo"] = None
            st.rerun()
        if col_nao.button("Cancelar", use_container_width=True):
            st.rerun()

    abrir_dialogo = False
    abrir_limpar = False
    arquivar_agora = False
    resetar_cfg = gerar_fake = apagar_fake = False
    with st.sidebar:
        st.header("Configurações")
        if senha is not None:
            if autorizado:
                st.success("Edição liberada.")
                if st.button(
                    "🔒 Bloquear edição",
                    use_container_width=True,
                    key="btn_bloquear",
                ):
                    st.session_state.autorizado = False
                    st.rerun()
            else:
                if st.button(
                    "🔓 Habilitar edição",
                    type="primary",
                    use_container_width=True,
                    key="btn_habilitar",
                ):
                    abrir_dialogo = True

        if autorizado:
            num = int(
                st.number_input(
                    "Quantidade de confrontos",
                    min_value=1,
                    max_value=MAX_CONFRONTOS,
                    step=1,
                    key="num_confrontos",
                )
            )
        else:
            num = int(st.session_state.get("num_confrontos", 1) or 1)
            st.caption(f"{num} confronto(s) — somente leitura")

        st.divider()
        if st.button("Atualizar parciais", use_container_width=True, key="btn_atualizar"):
            st.cache_data.clear()
            st.rerun()
        if autorizado:
            if st.button("Limpar tudo", use_container_width=True, key="btn_limpar"):
                abrir_limpar = True
            if _gsheets_configurado():
                if st.button("Arquivar rodada agora", use_container_width=True, key="btn_arquivar"):
                    arquivar_agora = True

        if _gsheets_configurado():
            with st.expander("🧪 Teste / Admin"):
                if st.button("Recriar abas de config", use_container_width=True, key="btn_reset_cfg"):
                    resetar_cfg = True
                if st.button("Gerar rodadas fake", use_container_width=True, key="btn_fake"):
                    gerar_fake = True
                if st.button("Apagar rodadas de teste", use_container_width=True, key="btn_del_fake"):
                    apagar_fake = True

    if abrir_dialogo:
        _dialogo_senha()
    if abrir_limpar:
        _dialogo_limpar()

    # Ações de teste/admin (mexem na planilha; rodam mesmo com o mercado aberto).
    if resetar_cfg or gerar_fake or apagar_fake:
        try:
            sh_admin = _planilha()
            if resetar_cfg:
                resetar_config_tabs(sh_admin)
                msg = "Abas participantes/confrontos/config recriadas no formato padrão."
            elif gerar_fake:
                _c = carregar_config()
                rr = list(range(_c["rodada_ini"], min(_c["rodada_ini"] + 4, _c["rodada_fim"] + 1)))
                feitas = gerar_rodadas_fake(sh_admin, _c, rr)
                msg = f"Rodadas fake geradas: {feitas}."
            else:
                apagadas = apagar_rodadas_teste(sh_admin)
                msg = f"Rodadas de teste apagadas: {apagadas or 'nenhuma'}."
            st.cache_data.clear()
            st.toast(msg, icon="✅")
            st.success(msg)
        except Exception as exc:  # noqa: BLE001
            st.toast("Erro na ação de teste.", icon="❌")
            st.error(f"Erro na ação de teste: {exc}")

    cfg = carregar_config()

    # Rodada em andamento (mercado fechado): dados dela são PARCIAIS até o mercado reabrir.
    _ms = carregar_mercado_status() or {}
    rodada_parcial = _ms.get("rodada_atual") if _ms.get("status_mercado") == 2 else None

    aba_vivo, aba_hist, aba_class = st.tabs(["🟢 Ao vivo", "📜 Histórico", "🏆 Classificação"])

    # ============================ AO VIVO ============================
    with aba_vivo:
        parciais = carregar_parciais()
        mercado = carregar_mercado()
        if not parciais or not mercado:
            if arquivar_agora:
                st.toast("Mercado aberto / sem parciais — nada para arquivar.", icon="⚠️")
            st.info("Sem parciais no momento (mercado aberto). O placar aparece quando a rodada começa. Veja o histórico e a classificação nas outras abas.")
        else:
            partidas = carregar_partidas()  # usado para escudos das selecoes (opcional)
            pesos = carregar_pesos_scouts()

            atletas = mercado.get("atletas", [])
            atletas_por_id = {
                a.get("atleta_id"): a for a in atletas if a.get("atleta_id") is not None
            }
            clubes_por_id = coletar_clubes(mercado, partidas, parciais)
            status_jogos = mapa_status_jogos(partidas)
            opcoes, id_para_label = opcoes_por_posicao(atletas, clubes_por_id)

            dados_confrontos: Dict[int, Dict] = {}
            confrontos_para_salvar: Dict[str, Dict] = {}

            leitura_ok = bool(st.session_state.get("leitura_ok", True))

            if autorizado and not leitura_ok:
                st.warning(
                    "Falha ao ler o estado salvo: as edições NÃO serão salvas nesta sessão "
                    "para proteger os dados. Clique em 'Atualizar parciais' para tentar de novo."
                )

            if autorizado:
                titulo_secao("Montar / editar times")
            else:
                st.markdown(
                    "<div class='edit-locked'>"
                    "<div class='ico'>🔒</div>"
                    "<div><div class='txt'>Edição bloqueada</div>"
                    "<div class='sub'>Clique em “Habilitar edição” na barra lateral e digite a senha para alterar os confrontos.</div>"
                    "</div></div>",
                    unsafe_allow_html=True,
                )

            for n in range(1, num + 1):
                salvo_conf = (
                    confrontos_salvos.get(str(n), {}) if isinstance(confrontos_salvos, dict) else {}
                )
                salvo_a, salvo_b = salvo_conf.get("a", {}), salvo_conf.get("b", {})
                nome_a_pad = salvo_a.get("nome") or f"Time {2 * n - 1}"
                nome_b_pad = salvo_b.get("nome") or f"Time {2 * n}"

                if autorizado:
                    with st.expander(f"Confronto {n}", expanded=False):
                        ce_a, ce_b = st.columns(2)
                        with ce_a:
                            nome_a, _, sel_a, ids_a = render_editor_time(
                                f"c{n}_a", nome_a_pad, "4-3-3", salvo_a, opcoes, id_para_label
                            )
                        with ce_b:
                            nome_b, _, sel_b, ids_b = render_editor_time(
                                f"c{n}_b", nome_b_pad, "4-3-3", salvo_b, opcoes, id_para_label
                            )
                    confrontos_para_salvar[str(n)] = {
                        "a": {"nome": nome_a, "formacao": st.session_state.get(f"formacao_c{n}_a"), "selecao": sel_a},
                        "b": {"nome": nome_b, "formacao": st.session_state.get(f"formacao_c{n}_b"), "selecao": sel_b},
                    }
                else:
                    nome_a, nome_b = nome_a_pad, nome_b_pad
                    ids_a = ids_da_selecao(salvo_a.get("selecao"))
                    ids_b = ids_da_selecao(salvo_b.get("selecao"))

                df_a = montar_tabela_escalacao(ids_a, parciais, atletas_por_id, clubes_por_id, pesos, status_jogos)
                df_b = montar_tabela_escalacao(ids_b, parciais, atletas_por_id, clubes_por_id, pesos, status_jogos)
                dados_confrontos[n] = {
                    "nome_a": nome_a, "df_a": df_a, "tot_a": total_time(df_a),
                    "nome_b": nome_b, "df_b": df_b, "tot_b": total_time(df_b),
                }

            titulo_secao("Placar ao vivo")
            ordem = list(range(1, num + 1))
            for i in range(0, len(ordem), 2):
                cols = st.columns(2)
                for col, n in zip(cols, ordem[i:i + 2]):
                    d = dados_confrontos[n]
                    with col:
                        st.markdown(
                            html_confronto(
                                n, d["nome_a"], d["df_a"], d["tot_a"],
                                d["nome_b"], d["df_b"], d["tot_b"],
                            ),
                            unsafe_allow_html=True,
                        )

            # Arquivamento manual da rodada (botão da sidebar, só com edição liberada)
            if arquivar_agora:
                rodada_num = (parciais or {}).get("rodada")
                atletas_pont = (parciais or {}).get("atletas", {}) or {}
                if not rodada_num or not atletas_pont:
                    st.toast("Sem parciais disponíveis (mercado aberto?). Nada para arquivar.", icon="⚠️")
                elif not confrontos_para_salvar:
                    st.toast("Nenhuma escalação para arquivar.", icon="⚠️")
                else:
                    try:
                        with st.spinner("Arquivando rodada na planilha..."):
                            linhas = montar_linhas_rodada(
                                rodada_num, confrontos_para_salvar, parciais,
                                atletas_por_id, clubes_por_id, pesos,
                            )
                            aba = arquivar_rodada_no_sheets(rodada_num, linhas)
                        st.toast(f"Rodada arquivada na aba '{aba}'.", icon="✅")
                        st.success(f"Rodada arquivada na aba '{aba}' da planilha.")
                    except Exception as exc:  # noqa: BLE001
                        st.toast("Erro ao arquivar a rodada.", icon="❌")
                        st.error(f"Erro ao arquivar a rodada: {exc}")

            if autorizado and leitura_ok:
                # Baseline = estado renderizado desta sessao na 1a vez que ela editou.
                if "_base_conf" not in st.session_state:
                    st.session_state._base_conf = json.loads(json.dumps(confrontos_para_salvar))
                    st.session_state._base_num = num
                base_conf = st.session_state.get("_base_conf", {}) or {}
                base_num = int(st.session_state.get("_base_num", num) or num)

                def _tot(conf: Dict) -> int:
                    return sum(
                        1
                        for lado in ("a", "b")
                        for v in ((conf.get(lado, {}) or {}).get("selecao") or {}).values()
                        if v
                    )

                mudou: Dict[str, Dict] = {}
                for n_str, conf in confrontos_para_salvar.items():
                    if conf != base_conf.get(n_str):
                        if _tot(conf) == 0 and _tot(base_conf.get(n_str, {}) or {}) > 0:
                            continue
                        mudou[n_str] = conf
                num_mudou = num != base_num

                if mudou or num_mudou:
                    remoto, ok = carregar_estado()
                    if ok:
                        remoto = remoto or {}
                        rconf = dict(remoto.get("confrontos", {}) or {})
                        for n_str, conf in mudou.items():
                            rconf[n_str] = conf
                            base_conf[n_str] = conf
                        novo_num = num if num_mudou else int(remoto.get("num_confrontos", num) or num)
                        novo = {"num_confrontos": novo_num, "confrontos": rconf}
                        salvar_escalacao_salva(novo)
                        st.session_state.dados_salvos = novo
                        st.session_state._base_conf = base_conf
                        st.session_state._base_num = num if num_mudou else base_num

    # ============================ HISTÓRICO ============================
    ini, fim = cfg.get("rodada_ini"), cfg.get("rodada_fim")

    with aba_hist:
        titulo_secao("Histórico por rodada")
        st.caption(f"Rodadas consideradas: {ini} a {fim} (configurável na aba `config` da planilha).")
        if not _gsheets_configurado():
            st.info("Configure o Google Sheets para ver o histórico arquivado.")
        else:
            try:
                sh = _planilha()
                rodadas = [r for r in _rodadas_disponiveis(sh)
                           if (ini is None or r >= ini) and (fim is None or r <= fim)]
                if not rodadas:
                    st.info("Nenhuma rodada arquivada dentro do range configurado.")
                else:
                    sel = st.selectbox("Rodada", rodadas, index=len(rodadas) - 1,
                                       format_func=lambda r: f"Rodada {r}")
                    if sel == rodada_parcial:
                        st.warning(f"⚠️ Rodada {sel} em andamento — pontuações **parciais** (ainda podem mudar).")
                    _mostrar_tabela_rodada(_ler_rodada(sh, sel))
            except Exception as exc:  # noqa: BLE001
                st.error(f"Erro ao ler o histórico: {exc}")

    # ============================ CLASSIFICAÇÃO ============================
    with aba_class:
        titulo_secao("Classificação")
        st.caption(f"Rodadas {ini}–{fim} · critérios: vitórias → empates → pontos feitos → menos pontos sofridos (derrotas não desempatam).")
        if not _gsheets_configurado():
            st.info("Configure o Google Sheets para ver a classificação.")
        else:
            try:
                linhas_class, rodadas = calcular_classificacao(_planilha(), ini, fim)
                if not linhas_class:
                    st.info("Nenhuma rodada arquivada dentro do range configurado.")
                else:
                    if rodada_parcial in rodadas:
                        st.warning(f"⚠️ Inclui a rodada {rodada_parcial} em andamento — classificação **parcial** (pode mudar até o fim da rodada).")
                    st.caption(f"Baseado em {len(rodadas)} rodada(s): {', '.join(str(r) for r in rodadas)}")
                    df_class = pd.DataFrame(linhas_class)
                    df_class.insert(0, "Pos", range(1, len(df_class) + 1))
                    st.dataframe(df_class, width="stretch", hide_index=True)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Erro ao calcular a classificação: {exc}")


if __name__ == "__main__":
    main()
