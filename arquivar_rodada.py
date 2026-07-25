"""Arquiva a rodada numa aba `rodada{N}` do Google Sheets, de forma acertiva.

Rodar via GitHub Actions (cron de hora em hora), independente do app estar aberto.

**Estratégia de captura** (o Cartola ajusta pontuações mesmo após os jogos):
enquanto o **mercado está fechado** (rodada em andamento/encerrando) e há
pontuações, o script **sobrescreve** a aba `rodada{N}` a cada execução. Assim,
a última gravação antes de o mercado reabrir — com o cron de hora em hora, ≤ 1h
antes da abertura — reflete as pontuações já ajustadas/finais. Quando o mercado
reabre (`status_mercado = 1`), o script não escreve mais e a aba fica congelada.

Cada linha: participante (nome do time no app), jogador, posição, clube e a
parcial (Σ scout × peso da liga), com o total de cada time.

Variáveis de ambiente (GitHub Secrets):
  GCP_SERVICE_ACCOUNT  -> JSON da conta de serviço (string)
  GSHEETS_KEY          -> ID da planilha (da URL)
  GSHEETS_WORKSHEET    -> nome da aba de estado (padrão: "estado")
"""

import json
import os
import pathlib
from datetime import datetime, timezone

import requests

API = "https://api.cartola.globo.com"
BASE_DIR = pathlib.Path(__file__).resolve().parent
POSICOES = {1: "GOL", 2: "LAT", 3: "ZAG", 4: "MEI", 5: "ATA"}


def get_json(url):
    """Retorna o JSON ou None (rede/resposta inválida — comum quando o mercado abre)."""
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as exc:  # noqa: BLE001
        print(f"Aviso: falha ao acessar {url}: {exc}")
        return None


def carregar_pesos():
    with open(BASE_DIR / "scouts_pontuacao.json", "r", encoding="utf-8") as f:
        return {str(k): float(v) for k, v in json.load(f).items()}


def parcial(scout, pesos):
    if not isinstance(scout, dict):
        return 0.0
    return sum(float(q) * pesos.get(k, 0.0) for k, q in scout.items())


def montar_linhas(rodada, confrontos, atletas_pont, atl_meta, clubes, pesos):
    quando = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    linhas = [[f"Rodada {rodada} — atualizado em {quando} (mercado fechado)"],
              ["Participante", "Jogador", "Posição", "Clube", "Parcial"]]
    for n in sorted(confrontos, key=lambda x: int(x)):
        conf = confrontos[n] or {}
        for lado in ("a", "b"):
            time = conf.get(lado, {}) or {}
            participante = (time.get("nome") or f"Confronto {n} - {lado.upper()}").strip()
            selecao = time.get("selecao", {}) or {}
            total = 0.0
            tem_jogador = False
            for _slot, aid in selecao.items():
                if not aid:
                    continue
                tem_jogador = True
                meta = atl_meta.get(aid, {})
                info_pont = atletas_pont.get(str(aid)) or atletas_pont.get(aid) or {}
                scout = info_pont.get("scout", {}) if isinstance(info_pont, dict) else {}
                pts = round(parcial(scout, pesos), 2)
                total += pts
                clube = clubes.get(meta.get("clube_id"), {})
                linhas.append([participante, meta.get("apelido", str(aid)),
                               POSICOES.get(meta.get("posicao_id"), ""),
                               clube.get("abreviacao", ""), pts])
            if tem_jogador:
                linhas.append([participante, "TOTAL", "", "", round(total, 2)])
        linhas.append([])  # separador entre confrontos
    return linhas


def main():
    status = get_json(f"{API}/mercado/status")
    if not status:
        print("Sem status do mercado. Nada a fazer.")
        return
    if status.get("status_mercado") != 2:
        print("Mercado aberto — histórico da rodada já está congelado. Nada a fazer.")
        return

    pontuados = get_json(f"{API}/atletas/pontuados")
    atletas_pont = (pontuados or {}).get("atletas", {}) or {}
    if not atletas_pont:
        print("Mercado fechado, mas ainda sem pontuações (rodada não começou). Nada a fazer.")
        return
    rodada = pontuados.get("rodada") or status.get("rodada_atual")
    if not rodada:
        print("Não foi possível determinar o número da rodada.")
        return

    # Conexão com o Sheets (import tardio: as checagens acima não precisam do gspread)
    import gspread
    gc = gspread.service_account_from_dict(json.loads(os.environ["GCP_SERVICE_ACCOUNT"]))
    sh = gc.open_by_key(os.environ["GSHEETS_KEY"])

    # Escalações salvas pelo app
    ws_estado = sh.worksheet(os.environ.get("GSHEETS_WORKSHEET", "estado"))
    estado = json.loads(ws_estado.acell("A1").value or "{}")
    confrontos = estado.get("confrontos", {}) or {}
    if not confrontos:
        print("Nenhuma escalação salva na aba de estado. Nada a arquivar.")
        return

    # Metadados dos atletas e clubes
    mercado = get_json(f"{API}/atletas/mercado") or {}
    atl_meta = {a.get("atleta_id"): a for a in mercado.get("atletas", []) if a.get("atleta_id")}
    clubes = {}
    for k, v in (mercado.get("clubes", {}) or {}).items():
        try:
            clubes[int(k)] = v
        except (TypeError, ValueError):
            pass

    pesos = carregar_pesos()
    linhas = montar_linhas(rodada, confrontos, atletas_pont, atl_meta, clubes, pesos)

    # Sobrescreve (ou cria) a aba rodada{N}. A última gravação antes da reabertura
    # do mercado = parciais já ajustadas.
    aba = f"rodada{rodada}"
    if aba in [w.title for w in sh.worksheets()]:
        ws = sh.worksheet(aba)
        ws.clear()
    else:
        ws = sh.add_worksheet(title=aba, rows=len(linhas) + 10, cols=6)
    ws.update(values=linhas, range_name="A1")
    print(f"✅ Aba '{aba}' atualizada ({len(linhas)} linhas).")


if __name__ == "__main__":
    main()
