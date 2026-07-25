# Cartola — Parciais

App [Streamlit](https://streamlit.io/) para acompanhar as **parciais ao vivo** do Cartola FC (Brasileirão), comparando até **4 confrontos (8 times)** num grid 2×2.

- Pontuação de cada jogador pelos **pesos da sua liga** (`scouts_pontuacao.json`): `Σ(scout × peso)`.
- Cards de confronto com tema escuro: barra de placar, coroa do vencedor, status ao vivo (🟢 jogou / 🔴 em andamento / cinza não iniciado) e ⭐ no maior pontuador.
- Auto-refresh a cada 10 minutos.
- Senha de edição e persistência em Google Sheets **opcionais** (via secrets).

Fonte de dados: API pública do Cartola (`https://api.cartola.globo.com`).

## Rodar localmente

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
streamlit run parciais.py
```

## Configuração

- **`scouts_pontuacao.json`** — mapa `código do scout → peso` da sua liga (ex.: `"G": 8.0`, `"CA": -2.0`). Já vem preenchido; edite se sua liga usar outra pontuação.
- **Senha / Google Sheets (opcional)** — copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml` e preencha. Sem esses secrets, o app é editável por qualquer um e a escalação é salva apenas localmente (`escalacao_salva.json`, efêmero).

## Deploy no Streamlit Community Cloud

1. Suba este repositório no GitHub.
2. Em [share.streamlit.io](https://share.streamlit.io), **Create app** → repositório = este repo, branch = `main`, **Main file path = `parciais.py`**.
3. (Opcional) **Settings → Secrets**: cole o conteúdo de `.streamlit/secrets.toml.example` preenchido para ativar senha e/ou Google Sheets.

> ⚠️ O Streamlit Cloud não tem disco persistente: sem Google Sheets, a escalação salva some a cada reinício do app. Para persistência real e compartilhada, configure o `[gsheets]` + `[gcp_service_account]`.

### Google Sheets (persistência)

1. No Google Cloud, habilite **Google Sheets API** e **Google Drive API**.
2. Crie uma **conta de serviço** e baixe a chave **JSON**.
3. Crie uma planilha e **compartilhe** com o `client_email` da conta de serviço (como Editor).
4. Preencha `[gcp_service_account]` (do JSON) e `[gsheets]` (`spreadsheet_key` = ID da planilha na URL, `worksheet` = `estado`) nos secrets.

## Arquivamento automático de rodadas (GitHub Actions)

O script `arquivar_rodada.py` grava, numa aba **`rodada{N}`** da mesma planilha, o **retrato final de cada rodada**: por time (participante = nome do time no app), a escalação com a parcial de cada jogador (posição, clube, pontos) e o total do time.

Como roda sozinho (o Streamlit Cloud não tem agendador), quem dispara é o workflow `.github/workflows/arquivar-rodada.yml` — de hora em hora. Ele só grava quando a **rodada está encerrada** (mercado fechado + todos os jogos terminados) e ignora se a aba `rodada{N}` já existe (idempotente). As escalações vêm da aba `estado` do Sheets — ou seja, **exige a persistência em Google Sheets ligada** no app.

**Configuração (uma vez):** em *GitHub → repositório → Settings → Secrets and variables → Actions*, crie:

| Secret | Valor |
|---|---|
| `GCP_SERVICE_ACCOUNT` | o **JSON inteiro** da conta de serviço (a mesma do app) |
| `GSHEETS_KEY` | o ID da planilha (da URL) |

Depois, em **Actions**, habilite os workflows. Dá para testar na hora em **Actions → Arquivar rodada → Run workflow** (fora de rodada encerrada, ele só loga "nada a fazer" — o esperado).

> Ajuste a frequência no `cron` do workflow se quiser checar mais perto do fim das rodadas.

