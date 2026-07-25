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
