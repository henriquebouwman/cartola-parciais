"""Arquiva a rodada numa aba `rodada{N}` do Google Sheets, de forma acertiva.

Rodar via GitHub Actions (cron de hora em hora), independente do app estar aberto.

**Estratégia de captura** (o Cartola ajusta pontuações mesmo após os jogos):
enquanto o **mercado está fechado** (rodada em andamento/encerrando) e há
pontuações, o script **sobrescreve** a aba `rodada{N}` a cada execução. Assim,
a última gravação antes de o mercado reabrir — com o cron de hora em hora, ≤ 1h
antes da abertura — reflete as pontuações já ajustadas/finais. Quando o mercado
reabre (`status_mercado = 1`), o script não escreve mais e a aba fica congelada.

**Consolidação** (garante a planilha igual ao Cartola): com o mercado aberto,
`/atletas/pontuados/{N}` devolve os scouts já fechados da rodada N. Então, a cada
execução com `status_mercado = 1`, o script confere a aba `rodada{N-1}` contra a
API e reescreve só as células divergentes (Parcial, Scouts, TOTAL), marcando o
título como "consolidado". É idempotente e não depende do horário em que o cron
roda. A consolidação usa os jogadores gravados na própria aba (coluna atleta_id,
com fallback por apelido+clube) — nunca a aba de estado, que já pode ter a
escalação da rodada seguinte. Se sobrar algo que não dá para corrigir sozinho
(ex.: jogador não encontrado), o script sai com código 1 uma vez, para o GitHub
avisar por e-mail.

Cada linha: participante (nome do time no app), jogador, posição, clube, a
parcial (Σ scout × peso da liga), os scouts e o atleta_id, com o total de cada time.

Variáveis de ambiente (GitHub Secrets):
  GCP_SERVICE_ACCOUNT  -> JSON da conta de serviço (string)
  GSHEETS_KEY          -> ID da planilha (da URL)
  GSHEETS_WORKSHEET    -> nome da aba de estado (padrão: "estado")
"""

import json
import os
import pathlib
import sys
from datetime import datetime, timezone

import requests

API = "https://api.cartola.globo.com"
BASE_DIR = pathlib.Path(__file__).resolve().parent
POSICOES = {1: "GOL", 2: "LAT", 3: "ZAG", 4: "MEI", 5: "ATA"}
CABECALHO = ["Participante", "Jogador", "Posição", "Clube", "Parcial", "Scouts", "atleta_id"]


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


def scouts_para_texto(scout):
    """Serializa o scout para a célula da planilha: "G:1;DS:3" (lido pelo app)."""
    if not isinstance(scout, dict):
        return ""
    partes = []
    for chave, qtd in scout.items():
        try:
            q = int(float(qtd))
        except (TypeError, ValueError):
            continue
        if q:
            partes.append(f"{chave}:{q}")
    return ";".join(partes)


def montar_linhas(rodada, confrontos, atletas_pont, atl_meta, clubes, pesos):
    quando = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    linhas = [[f"Rodada {rodada} — atualizado em {quando} (mercado fechado)"],
              CABECALHO]
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
                if not isinstance(info_pont, dict):
                    info_pont = {}
                scout = info_pont.get("scout", {})
                pts = round(parcial(scout, pesos), 2)
                total += pts
                # Fallback para /atletas/pontuados quando o mercado vem vazio (mercado fechado).
                apelido = meta.get("apelido") or info_pont.get("apelido") or str(aid)
                posicao_id = meta.get("posicao_id") or info_pont.get("posicao_id")
                clube_id = meta.get("clube_id") or info_pont.get("clube_id")
                clube = clubes.get(clube_id, {}) if clube_id else {}
                linhas.append([participante, apelido,
                               POSICOES.get(posicao_id, ""),
                               clube.get("abreviacao", ""), pts,
                               scouts_para_texto(scout), str(aid)])
            if tem_jogador:
                linhas.append([participante, "TOTAL", "", "", round(total, 2), "", ""])
        linhas.append([])  # separador entre confrontos
    return linhas


def consolidar(status):
    """Mercado aberto: deixa a aba da rodada que acabou igual a /atletas/pontuados/{N}.

    Retorna o código de saída (1 = sobraram divergências não corrigíveis, 1ª vez)."""
    from checar_rodadas import abrir_planilha, aplicar_updates, checar_rodada, ler_abas

    rodada_atual = int(status.get("rodada_atual") or 0)
    if status.get("status_mercado") == 1:
        alvo = rodada_atual - 1
    elif status.get("game_over"):
        alvo = rodada_atual  # fim de temporada: a última rodada não tem "próxima"
    else:
        print(f"Mercado em status {status.get('status_mercado')} (manutenção?). Nada a fazer.")
        return 0
    if alvo < 1:
        print("Nenhuma rodada anterior para consolidar.")
        return 0

    dados = get_json(f"{API}/atletas/pontuados/{alvo}")
    if not (dados or {}).get("atletas"):
        print(f"API sem pontuações da rodada {alvo}. Nada a consolidar agora.")
        return 0

    sh = abrir_planilha()
    abas = ler_abas(sh, {alvo})
    if alvo not in abas:
        print(f"Aba rodada{alvo} não existe (rodada não foi arquivada). Nada a consolidar.")
        return 0

    pesos = carregar_pesos()
    resumo, divs = checar_rodada(alvo, abas[alvo], pesos, {}, dados=dados)
    titulo_atual = resumo.get("titulo", "")
    ups = resumo.get("updates", [])

    pendentes = divs
    if ups:
        aplicar_updates(sh, alvo, ups)
        print(f"Rodada {alvo}: {len(ups)} célula(s) corrigida(s) com os valores finais da API:")
        for d in divs:
            print(f"   L{d['linha']} {d['participante']} | {d['jogador']} | {d['tipo']}: {d['detalhe']}")
        # Confere de novo o que ficou na planilha.
        _r2, pendentes = checar_rodada(alvo, ler_abas(sh, {alvo})[alvo], pesos, {}, dados=dados)
    else:
        print(f"Rodada {alvo}: nada a corrigir automaticamente "
              f"({resumo.get('ok')}/{resumo.get('jogadores')} jogadores batem com a API).")

    quando = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if pendentes:
        novo = f"Rodada {alvo} — consolidado em {quando} ({len(pendentes)} pendência(s) — ver log do robô)"
    else:
        novo = f"Rodada {alvo} — consolidado em {quando} (scouts finais da API)"
    ja_consolidada = "consolidado" in titulo_atual
    ja_avisou = "pendência" in titulo_atual
    if ups or not ja_consolidada or (bool(pendentes) != ja_avisou):
        aplicar_updates(sh, alvo, [], titulo=novo)

    if pendentes:
        print(f"⚠️  {len(pendentes)} divergência(s) que o robô não conseguiu corrigir:")
        for d in pendentes:
            print(f"   L{d['linha']} {d['participante']} | {d['jogador']} | {d['tipo']}: {d['detalhe']}")
        print(f"   Rode `python checar_rodadas.py --rodadas {alvo}` e ajuste manualmente.")
        return 0 if ja_avisou else 1  # falha (e-mail do GitHub) só na 1ª vez
    print(f"✅ Rodada {alvo} consolidada.")
    return 0


def main():
    status = get_json(f"{API}/mercado/status")
    if not status:
        print("Sem status do mercado. Nada a fazer.")
        return 0
    if status.get("status_mercado") != 2:
        return consolidar(status)

    pontuados = get_json(f"{API}/atletas/pontuados")
    atletas_pont = (pontuados or {}).get("atletas", {}) or {}
    if not atletas_pont:
        print("Mercado fechado, mas ainda sem pontuações (rodada não começou). Nada a fazer.")
        return 0
    rodada = pontuados.get("rodada") or status.get("rodada_atual")
    if not rodada:
        print("Não foi possível determinar o número da rodada.")
        return 0

    # Conexão com o Sheets (import tardio: as checagens acima não precisam do gspread)
    from checar_rodadas import abrir_planilha
    sh = abrir_planilha()

    # Escalações salvas pelo app
    nome_estado = os.environ.get("GSHEETS_WORKSHEET", "estado")
    titulos = [w.title for w in sh.worksheets()]
    if nome_estado not in titulos:
        print(f"Aba de estado '{nome_estado}' ainda não existe (o app não salvou nada). Nada a arquivar.")
        return 0
    ws_estado = sh.worksheet(nome_estado)
    estado = json.loads(ws_estado.acell("A1").value or "{}")
    escalacoes = estado.get("escalacoes", {}) or {}
    if not escalacoes:
        print("Nenhuma escalação salva na aba de estado. Nada a arquivar.")
        return 0

    # Config da planilha: apelidos (aba participantes) + tabela de confrontos.
    apelidos = {}
    if "participantes" in titulos:
        for row in sh.worksheet("participantes").get_all_values()[1:]:
            if len(row) >= 2 and str(row[1]).strip():
                nome = str(row[1]).strip()
                apelidos[nome] = (str(row[2]).strip() if len(row) >= 3 and str(row[2]).strip()
                                  else nome)

    pares = []
    if "confrontos" in titulos:
        for row in sh.worksheet("confrontos").get_all_values()[1:]:
            if not row or not str(row[0]).strip().isdigit():
                continue
            if int(str(row[0]).strip()) != int(rodada):
                continue
            cells = [str(c).strip() for c in row[1:]]
            pares = [(cells[i], cells[i + 1]) for i in range(0, 6, 2)
                     if i + 1 < len(cells) and cells[i] and cells[i + 1]]
            break
    if not pares:
        print(f"Sem confrontos configurados para a rodada {rodada}. Nada a arquivar.")
        return 0

    confrontos = {}
    for i, (a, b) in enumerate(pares, start=1):
        ea, eb = escalacoes.get(a) or {}, escalacoes.get(b) or {}
        confrontos[str(i)] = {
            "a": {"nome": apelidos.get(a, a), "selecao": ea.get("selecao", {}) or {}},
            "b": {"nome": apelidos.get(b, b), "selecao": eb.get("selecao", {}) or {}},
        }

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
        if ws.col_count < len(CABECALHO):
            ws.add_cols(len(CABECALHO) - ws.col_count)
    else:
        ws = sh.add_worksheet(title=aba, rows=len(linhas) + 10, cols=len(CABECALHO))
    ws.update(values=linhas, range_name="A1")
    print(f"✅ Aba '{aba}' atualizada ({len(linhas)} linhas).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
