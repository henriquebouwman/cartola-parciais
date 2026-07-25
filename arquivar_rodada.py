"""Arquiva a rodada encerrada numa aba `rodada{N}` do Google Sheets.

Pensado para rodar via GitHub Actions (cron), independente do app estar aberto:
- Lê as escalações que o app salvou na aba `estado` do Sheets.
- Busca as pontuações finais na API do Cartola (só quando a rodada está
  encerrada: mercado fechado + todos os jogos terminados).
- Calcula a parcial de cada jogador pelos pesos da liga (scouts_pontuacao.json).
- Cria a aba `rodada{N}` com, por time: participante (nome do time), jogador,
  posição, clube e parcial — mais o total de cada time.

Idempotente: se a aba `rodada{N}` já existir, não faz nada.

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

ENCERRADO = ["encerr", "fim", "final", "terminad"]


def get_json(url):
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    r.raise_for_status()
    return r.json()


def carregar_pesos():
    with open(BASE_DIR / "scouts_pontuacao.json", "r", encoding="utf-8") as f:
        return {str(k): float(v) for k, v in json.load(f).items()}


def jogo_encerrado(p):
    for k in ("status_transmissao_tr", "periodo_tr", "status", "periodo"):
        v = p.get(k)
        if isinstance(v, str) and any(x in v.lower() for x in ENCERRADO):
            return True
    return False


def rodada_encerrada(partidas):
    lista = partidas.get("partidas") or []
    if not lista:
        return False
    return all(jogo_encerrado(p) for p in lista)


def parcial(scout, pesos):
    if not isinstance(scout, dict):
        return 0.0
    return sum(float(q) * pesos.get(k, 0.0) for k, q in scout.items())


def main():
    status = get_json(f"{API}/mercado/status")
    if status.get("status_mercado") != 2:
        print("Mercado aberto (rodada não está em andamento/encerramento). Nada a fazer.")
        return

    partidas = get_json(f"{API}/partidas")
    if not rodada_encerrada(partidas):
        print("Rodada ainda não encerrada (há jogos em andamento). Nada a fazer.")
        return

    pontuados = get_json(f"{API}/atletas/pontuados")
    atletas_pont = pontuados.get("atletas", {}) or {}
    rodada = pontuados.get("rodada") or status.get("rodada_atual")
    if not rodada:
        print("Não foi possível determinar o número da rodada.")
        return

    # Conexão com o Sheets (import tardio: as checagens acima não precisam do gspread)
    import gspread
    info = json.loads(os.environ["GCP_SERVICE_ACCOUNT"])
    gc = gspread.service_account_from_dict(info)
    sh = gc.open_by_key(os.environ["GSHEETS_KEY"])

    aba = f"rodada{rodada}"
    if aba in [w.title for w in sh.worksheets()]:
        print(f"Aba '{aba}' já existe — nada a fazer (idempotente).")
        return

    # Escalações salvas pelo app
    ws_estado = sh.worksheet(os.environ.get("GSHEETS_WORKSHEET", "estado"))
    estado = json.loads(ws_estado.acell("A1").value or "{}")
    confrontos = estado.get("confrontos", {}) or {}
    if not confrontos:
        print("Nenhuma escalação salva na aba de estado. Nada a arquivar.")
        return

    # Metadados dos atletas e clubes
    mercado = get_json(f"{API}/atletas/mercado")
    atl_meta = {a.get("atleta_id"): a for a in mercado.get("atletas", []) if a.get("atleta_id")}
    clubes = {}
    for k, v in (mercado.get("clubes", {}) or {}).items():
        try:
            clubes[int(k)] = v
        except (TypeError, ValueError):
            pass

    pesos = carregar_pesos()
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

    ws = sh.add_worksheet(title=aba, rows=len(linhas) + 5, cols=6)
    ws.update(values=linhas, range_name="A1")
    print(f"✅ Aba '{aba}' criada com {len(linhas)} linhas.")


if __name__ == "__main__":
    main()
