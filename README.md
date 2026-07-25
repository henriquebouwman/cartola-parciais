# Fantasy Draft

App [Streamlit](https://streamlit.io/) de uma **liga de fantasy (draft)** do Cartola FC (Brasileirão): **6 participantes** disputam **3 confrontos por rodada**, seguindo a tabela do turno.

- **Pontuação** de cada jogador pelos **pesos da liga** (`scouts_pontuacao.json`): `Σ(scout × peso)`.
- Cards de confronto com tema escuro: barra de placar, coroa do vencedor, status ao vivo (🟢 jogou / 🔴 em andamento / cinza não iniciado) e ⭐ no maior pontuador.
- Auto-refresh a cada 10 minutos.
- Três abas: **Ao vivo** (placar), **Histórico** (cada rodada arquivada) e **Classificação** do turno (V, E, D, pontos feitos e sofridos — ordena por vitórias → empates → pontos feitos → menos pontos sofridos). Quando incluem a **rodada em andamento**, sinalizam que é **parcial**.
- **Configuração centralizada na planilha** (criada na 1ª execução, editável direto no Sheets; o app relê a cada ~2 min):
  - **`participantes`** — `Posição | Nome | Apelido | Senha` (o **apelido** é o que aparece no dash).
  - **`confrontos`** — `Rodada | Casa 1 | Fora 1 | Casa 2 | Fora 2 | Casa 3 | Fora 3` (a tabela do turno).
  - **`config`** — `rodada_inicial`, `rodada_final` (range da classificação/histórico) e `senha_master`.
- Persistência em Google Sheets (via secrets do Streamlit).

Na sidebar há uma seção **🧪 Teste / Admin** (temporária) para: recriar as abas de config no formato padrão, gerar **rodadas fake** (marcadas `[TESTE]`) e apagar só essas rodadas de teste.

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

O script `arquivar_rodada.py` grava, numa aba **`rodada{N}`** da mesma planilha, o **retrato de cada rodada**: por time (participante = nome do time no app), a escalação com a parcial de cada jogador (posição, clube, pontos) e o total do time.

**Captura acertiva:** como o Cartola ajusta pontuações mesmo depois dos jogos, o script **sobrescreve** a aba `rodada{N}` a cada execução **enquanto o mercado está fechado** (rodada em andamento/encerrando). Com o cron de hora em hora, a **última gravação antes de o mercado reabrir (≤ 1h)** reflete as pontuações já ajustadas/finais. Quando o mercado reabre, o script para de escrever e a aba fica **congelada** no valor final.

Quem dispara é o workflow `.github/workflows/arquivar-rodada.yml` (de hora em hora), independente do app estar aberto. As escalações vêm da aba `estado` do Sheets — ou seja, **exige a persistência em Google Sheets ligada** no app.

Há também um botão **"Arquivar rodada agora"** na sidebar do app (aparece só com a **edição liberada pela senha** e o Sheets configurado), para arquivar sob demanda a rodada atual — convive com o robô automático (ambos gravam/atualizam a mesma aba `rodada{N}`).

**Configuração (uma vez):** em *GitHub → repositório → Settings → Secrets and variables → Actions*, crie:

| Secret | Valor |
|---|---|
| `GCP_SERVICE_ACCOUNT` | o **JSON inteiro** da conta de serviço (a mesma do app) |
| `GSHEETS_KEY` | o ID da planilha (da URL) |

Depois, em **Actions**, habilite os workflows. Dá para testar na hora em **Actions → Arquivar rodada → Run workflow** (fora de rodada encerrada, ele só loga "nada a fazer" — o esperado).

> Ajuste a frequência no `cron` do workflow se quiser checar mais perto do fim das rodadas.

