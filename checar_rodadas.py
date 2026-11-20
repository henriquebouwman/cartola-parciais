"""Confere as abas `rodada{N}` da planilha contra a API do Cartola.

Para cada jogador arquivado, compara os scouts e a parcial gravados na planilha
com o que a API devolve hoje em `/atletas/pontuados/{rodada}` (já consolidado),
recalculando a parcial com os pesos da liga (`scouts_pontuacao.json`).
Também confere se a linha TOTAL de cada time bate com a soma dos jogadores.

Por padrão só LÊ a planilha. Com `--corrigir` (modo Sheets), reescreve apenas as
células divergentes (Parcial, Scouts e TOTAL) com os valores da API, depois de
salvar um backup local das abas alteradas em `backup_rodadas_<data>.json`.

Uso:
  # Direto do Google Sheets (mesmas credenciais do app / robô):
  python checar_rodadas.py                       # todas as abas rodada{N}
  python checar_rodadas.py --rodadas 30 31 35    # só algumas
  python checar_rodadas.py --corrigir            # corrige as divergências na planilha

  # A partir de um .xlsx baixado da planilha (Arquivo → Fazer download → .xlsx):
  python checar_rodadas.py --xlsx planilha.xlsx

Credenciais (modo Sheets), na ordem:
  1. env GCP_SERVICE_ACCOUNT (JSON) + GSHEETS_KEY  (igual ao GitHub Actions)
  2. .streamlit/secrets.toml  ([gcp_service_account] + [gsheets].spreadsheet_key)

Saída: resumo no terminal + `checagem_rodadas.csv` (uma linha por divergência).
"""

import argparse
import csv
import json
import os
import pathlib
import re
import sys
import time
import unicodedata
from collections import defaultdict

import requests

API = "https://api.cartola.globo.com"
BASE_DIR = pathlib.Path(__file__).resolve().parent
TOL = 0.01  # tolerância para comparar pontos
_SH = None  # planilha aberta (modo Sheets), usada pelo --corrigir


# ----------------------------------------------------------------- utilidades
def get_json(url, tentativas=3):
    for i in range(tentativas):
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            r.raise_for_status()
            return r.json()
        except Exception as exc:  # noqa: BLE001
            if i == tentativas - 1:
                print(f"  ! falha ao acessar {url}: {exc}")
                return None
            time.sleep(1.5 * (i + 1))


def norm(txt):
    """Minúsculo, sem acento e sem espaços extras (para casar apelidos)."""
    txt = unicodedata.normalize("NFKD", str(txt or ""))
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", txt).strip().lower()


def num(x):
    try:
        return float(str(x).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def carregar_pesos():
    with open(BASE_DIR / "scouts_pontuacao.json", "r", encoding="utf-8") as f:
        return {str(k): float(v) for k, v in json.load(f).items()}


def parcial(scout, pesos):
    return round(sum(float(q) * pesos.get(k, 0.0) for k, q in (scout or {}).items()), 2)


def texto_para_scouts(texto):
    """Mesmo parser do app: "G:1;DS:3" -> {"G": 1, "DS": 3}."""
    scout = {}
    for parte in str(texto or "").split(";"):
        chave, _, qtd = parte.partition(":")
        chave = chave.strip().upper()
        if not chave:
            continue
        try:
            q = int(float(qtd))
        except (TypeError, ValueError):
            continue
        if q:
            scout[chave] = q
    return scout


def limpar_scout(scout):
    out = {}
    for k, v in (scout or {}).items():
        try:
            q = int(float(v))
        except (TypeError, ValueError):
            continue
        if q:
            out[str(k).upper()] = q
    return out


def scout_txt(s):
    return ";".join(f"{k}:{v}" for k, v in sorted(s.items())) or "-"


def diff_scouts(planilha, api):
    """"DS 3→4; G +1" — só as chaves que mudaram."""
    partes = []
    for k in sorted(set(planilha) | set(api)):
        a, b = planilha.get(k, 0), api.get(k, 0)
        if a != b:
            partes.append(f"{k} {a}→{b}")
    return "; ".join(partes)


# ------------------------------------------------------------ leitura da planilha
def abrir_planilha():
    """Abre a planilha com as credenciais do env (Actions) ou do secrets.toml (local)."""
    import gspread

    if os.environ.get("GCP_SERVICE_ACCOUNT") and os.environ.get("GSHEETS_KEY"):
        cred = json.loads(os.environ["GCP_SERVICE_ACCOUNT"])
        key = os.environ["GSHEETS_KEY"]
    else:
        caminho = BASE_DIR / ".streamlit" / "secrets.toml"
        if not caminho.exists():
            sys.exit("Sem credenciais: defina GCP_SERVICE_ACCOUNT/GSHEETS_KEY ou crie "
                     ".streamlit/secrets.toml (ou use --xlsx).")
        try:
            import tomllib
        except ModuleNotFoundError:  # Python < 3.11
            import tomli as tomllib
        with open(caminho, "rb") as f:
            sec = tomllib.load(f)
        cred = dict(sec["gcp_service_account"])
        key = sec["gsheets"].get("spreadsheet_key")
        if not key and sec["gsheets"].get("spreadsheet_url"):
            key = re.search(r"/d/([\w-]+)", sec["gsheets"]["spreadsheet_url"]).group(1)
    return gspread.service_account_from_dict(cred).open_by_key(key)


def ler_abas(sh, rodadas_filtro=None):
    """{N: valores} das abas rodada{N} numa única requisição (batchGet, valores crus)."""
    nums = sorted(int(m.group(1)) for w in sh.worksheets()
                  if (m := re.fullmatch(r"rodada(\d+)", w.title.strip())))
    if rodadas_filtro:
        nums = [n for n in nums if n in rodadas_filtro]
    if not nums:
        return {}
    resp = sh.values_batch_get([f"'rodada{n}'" for n in nums],
                               params={"valueRenderOption": "UNFORMATTED_VALUE"})
    return {n: vr.get("values", []) for n, vr in zip(nums, resp.get("valueRanges", []))}


def aplicar_updates(sh, n, updates, titulo=None):
    """Reescreve só as células indicadas da aba rodada{N} (e o título, se dado)."""
    data = [{"range": f"'rodada{n}'!{cel}", "values": [[val]]} for cel, val in updates]
    if titulo:
        data.append({"range": f"'rodada{n}'!A1", "values": [[titulo]]})
    if data:
        sh.values_batch_update({"valueInputOption": "RAW", "data": data})
    return len(data)


def abas_do_sheets(rodadas_filtro):
    global _SH
    _SH = abrir_planilha()
    return ler_abas(_SH, rodadas_filtro)


def abas_do_xlsx(caminho, rodadas_filtro):
    from openpyxl import load_workbook

    wb = load_workbook(caminho, read_only=True, data_only=True)
    out = {}
    for nome in wb.sheetnames:
        m = re.fullmatch(r"rodada(\d+)", nome.strip())
        if not m:
            continue
        n = int(m.group(1))
        if rodadas_filtro and n not in rodadas_filtro:
            continue
        out[n] = [["" if c is None else c for c in row] for row in wb[nome].iter_rows(values_only=True)]
    return dict(sorted(out.items()))


def parse_aba(valores):
    """Mesmo layout lido pelo app: título, cabeçalho, jogadores + TOTAL por time."""
    cab = [str(c).strip().lower() for c in (valores[1] if len(valores) > 1 else [])]
    tem_scouts = len(cab) > 5 and cab[5].startswith("scout")
    tem_id = len(cab) > 6 and cab[6] == "atleta_id"
    titulo = str(valores[0][0]) if valores and valores[0] else ""

    times, atual, jogadores = [], None, []
    for i, row in enumerate(valores[2:], start=3):
        cells = [str(c).strip() for c in row]
        if not any(cells):
            continue
        part = cells[0] if cells else ""
        jog = cells[1] if len(cells) > 1 else ""
        if jog.upper() == "TOTAL":
            times.append({"participante": part or atual or "", "jogadores": jogadores,
                          "total": num(cells[4]) if len(cells) > 4 else 0.0, "linha": i})
            atual, jogadores = None, []
        else:
            atual = part or atual
            jogadores.append({
                "linha": i, "participante": atual, "jogador": jog,
                "posicao": cells[2] if len(cells) > 2 else "",
                "clube": cells[3] if len(cells) > 3 else "",
                "pts": num(cells[4]) if len(cells) > 4 and cells[4] else 0.0,
                "scout": texto_para_scouts(cells[5] if len(cells) > 5 else "") if tem_scouts else None,
                "id": (cells[6].split(".")[0] if tem_id and len(cells) > 6 and cells[6] else ""),
            })
    return titulo, tem_scouts, times


# --------------------------------------------------------------- comparação
def indexar_api(dados):
    """Índices por (apelido, clube) e por apelido, a partir de /atletas/pontuados/{r}."""
    clubes = {int(k): v.get("abreviacao", "") for k, v in (dados.get("clubes") or {}).items()}
    por_id, por_nome_clube, por_nome = {}, {}, defaultdict(list)
    for aid, a in (dados.get("atletas") or {}).items():
        reg = {"id": aid, "apelido": a.get("apelido", ""),
               "clube": clubes.get(a.get("clube_id"), ""),
               "scout": limpar_scout(a.get("scout")),
               "entrou": a.get("entrou_em_campo")}
        por_id[str(aid)] = reg
        por_nome_clube[(norm(reg["apelido"]), norm(reg["clube"]))] = reg
        por_nome[norm(reg["apelido"])].append(reg)
    return por_id, por_nome_clube, por_nome


def casar(j, idx):
    """(registro da API ou None, como casou). Ordem: atleta_id → apelido+clube → apelido único.

    Com atleta_id gravado, ausência na API = não pontuou (não cai no fallback por nome)."""
    por_id, por_nome_clube, por_nome = idx
    if j.get("id"):
        return por_id.get(j["id"]), "atleta_id"
    reg = por_nome_clube.get((norm(j["jogador"]), norm(j["clube"])))
    if reg is not None:
        return reg, "apelido+clube"
    cands = por_nome.get(norm(j["jogador"]), [])
    if len(cands) == 1:
        return cands[0], f"só apelido (clube API={cands[0]['clube']})"
    if len(cands) > 1:
        return None, "AMBÍGUO"
    return None, "não encontrado"


def checar_rodada(n, valores, pesos, clubes_global, dados=None):
    """Compara a aba com a API. `updates` = [(célula A1, valor)] para deixar a aba igual à API."""
    titulo, tem_scouts, times = parse_aba(valores)
    if dados is None:
        dados = get_json(f"{API}/atletas/pontuados/{n}")
    if not dados or not dados.get("atletas"):
        return {"rodada": n, "erro": "API sem dados para a rodada"}, []
    if dados.get("clubes") is None:
        dados["clubes"] = clubes_global
    idx = indexar_api(dados)

    divs, n_jog, n_ok = [], 0, 0
    updates = []  # (célula A1, valor) a reescrever com o valor da API
    for t in times:
        soma_planilha = 0.0
        soma_api = 0.0
        for j in t["jogadores"]:
            n_jog += 1
            soma_planilha += j["pts"]
            reg, como = casar(j, idx)
            if como == "AMBÍGUO":
                divs.append(_div(n, t, j, "AMBÍGUO", "mais de um atleta com esse apelido na API"))
                soma_api += j["pts"]
                continue
            # Com atleta_id, ausência na API = não pontuou (valor da API é 0/sem scouts).
            confiavel = reg is not None or como == "atleta_id"
            api_scout = reg["scout"] if reg else {}
            api_pts = parcial(api_scout, pesos)
            soma_api += api_pts if confiavel else j["pts"]  # sem match: mantém o valor da planilha

            problemas = []
            if tem_scouts and j["scout"] != api_scout:
                problemas.append(("SCOUT", diff_scouts(j["scout"], api_scout)))
            if abs(j["pts"] - api_pts) > TOL:
                problemas.append(("PARCIAL", f"planilha {j['pts']:.2f} vs API {api_pts:.2f} "
                                             f"(Δ {api_pts - j['pts']:+.2f})"))
            if not confiavel and (j["pts"] or (j["scout"] or {})):
                problemas.append(("NÃO ENCONTRADO", "jogador não aparece em pontuados/{r} "
                                                    "mas a planilha tem pontos/scouts"))
            if not problemas:
                n_ok += 1
            elif confiavel:
                updates.append((f"E{j['linha']}", api_pts))
                if tem_scouts:
                    updates.append((f"F{j['linha']}", ";".join(f"{k}:{v}" for k, v in sorted(api_scout.items()))))
            for tipo, det in problemas:
                d = _div(n, t, j, tipo, det)
                d.update(scout_planilha=scout_txt(j["scout"] or {}) if tem_scouts else "(sem coluna)",
                         scout_api=scout_txt(api_scout), pts_planilha=j["pts"], pts_api=api_pts,
                         match=como)
                divs.append(d)

        if abs(round(soma_api, 2) - t["total"]) > TOL:
            updates.append((f"E{t['linha']}", round(soma_api, 2)))
        if abs(round(soma_planilha, 2) - t["total"]) > TOL:
            divs.append({"rodada": n, "linha": t["linha"], "participante": t["participante"],
                         "jogador": "TOTAL", "tipo": "TOTAL INCONSISTENTE",
                         "detalhe": f"TOTAL {t['total']:.2f} ≠ soma dos jogadores {soma_planilha:.2f}"})

    resumo = {"rodada": n, "titulo": titulo, "tem_scouts": tem_scouts, "jogadores": n_jog,
              "ok": n_ok, "divergentes": n_jog - n_ok, "itens": len(divs), "updates": updates}
    # Impacto no placar: total por time planilha vs API
    resumo["times"] = []
    for t in times:
        tot_api = 0.0
        for j in t["jogadores"]:
            reg, como = casar(j, idx)
            confiavel = reg is not None or como == "atleta_id"
            tot_api += parcial(reg["scout"], pesos) if reg else (0.0 if confiavel else j["pts"])
        resumo["times"].append((t["participante"], t["total"], round(tot_api, 2)))
    return resumo, divs


def _div(n, t, j, tipo, det):
    return {"rodada": n, "linha": j["linha"], "participante": t["participante"],
            "jogador": j["jogador"], "clube": j["clube"], "tipo": tipo, "detalhe": det}


def corrigir(abas, resumos):
    """Backup local das abas afetadas + batch update só das células divergentes."""
    from datetime import datetime

    alvo = {r["rodada"]: r["updates"] for r in resumos if r.get("updates")}
    if not alvo:
        print("\nNada a corrigir.")
        return
    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = BASE_DIR / f"backup_rodadas_{carimbo}.json"
    with open(backup, "w", encoding="utf-8") as f:
        json.dump({f"rodada{n}": abas[n] for n in alvo}, f, ensure_ascii=False, indent=1, default=str)
    print(f"\nBackup das abas {', '.join(f'rodada{n}' for n in alvo)} em {backup.name}")

    total = sum(aplicar_updates(_SH, n, ups) for n, ups in alvo.items())
    print(f"✅ {total} célula(s) corrigida(s) em {len(alvo)} aba(s).")


# ---------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--xlsx", help="ler de um .xlsx baixado em vez do Google Sheets")
    ap.add_argument("--rodadas", type=int, nargs="*", help="só estas rodadas")
    ap.add_argument("--saida", default="checagem_rodadas.csv")
    ap.add_argument("--corrigir", action="store_true",
                    help="reescreve na planilha as células divergentes com os valores da API")
    args = ap.parse_args()

    if args.corrigir and args.xlsx:
        sys.exit("--corrigir só funciona lendo direto do Google Sheets (sem --xlsx).")
    filtro = set(args.rodadas or [])
    abas = abas_do_xlsx(args.xlsx, filtro) if args.xlsx else abas_do_sheets(filtro)
    if not abas:
        sys.exit("Nenhuma aba rodada{N} encontrada.")
    print(f"Abas encontradas: {', '.join(f'rodada{n}' for n in abas)}\n")

    pesos = carregar_pesos()
    clubes_global = (get_json(f"{API}/clubes") or {})
    todas, resumos = [], []
    for n, valores in abas.items():
        resumo, divs = checar_rodada(n, valores, pesos, clubes_global)
        resumos.append(resumo)
        todas.extend(divs)
        if "erro" in resumo:
            print(f"rodada{n}: ⚠️  {resumo['erro']}")
            continue
        flag = "✅" if not divs else "❌"
        print(f"rodada{n}: {flag} {resumo['ok']}/{resumo['jogadores']} jogadores batem"
              + ("" if resumo["tem_scouts"] else "  (aba sem coluna Scouts: só parcial conferida)"))
        for d in divs:
            print(f"   L{d['linha']:<4} {d['participante'][:14]:<14} {d['jogador'][:22]:<22} "
                  f"{d['tipo']:<20} {d['detalhe']}")
        mudou = [(p, a, b) for p, a, b in resumo["times"] if abs(a - b) > TOL]
        for p, a, b in mudou:
            print(f"   ↳ total {p}: planilha {a:.2f} → API {b:.2f} (Δ {b - a:+.2f})")
        if divs:
            print()

    campos = ["rodada", "linha", "participante", "jogador", "clube", "tipo", "detalhe",
              "scout_planilha", "scout_api", "pts_planilha", "pts_api", "match"]
    with open(args.saida, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(todas)
    rod_div = sorted({d["rodada"] for d in todas})
    if args.corrigir:
        corrigir(abas, resumos)
    print(f"\nResumo: {len(todas)} divergência(s) em {len(rod_div)} rodada(s)"
          + (f" ({', '.join(map(str, rod_div))})" if rod_div else "")
          + f". Detalhes em {args.saida}")


if __name__ == "__main__":
    main()
