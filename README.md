# Fantasy Draft

App [Streamlit](https://streamlit.io/) de uma **liga de fantasy (draft)** do Cartola FC (Brasileirão): **6 participantes** disputam **3 confrontos por rodada**, seguindo a tabela do turno.

- **Pontuação** de cada jogador pelos **pesos da liga** (`scouts_pontuacao.json`): `Σ(scout × peso)`.
- Cards de confronto com tema escuro: barra de placar, **diferença de pontos** no cabeçalho (quem lidera e por quanto), coroa do vencedor, status ao vivo (🟢 jogou / 🔴 em andamento / cinza não iniciado) e ⭐ no maior pontuador.
- Auto-refresh a cada 10 minutos.
- Três abas: **Ao vivo** (placar), **Histórico** (cada rodada arquivada) e **Classificação** do turno (V, E, D, pontos feitos e sofridos — ordena por vitórias → empates → pontos feitos → menos pontos sofridos). Quando incluem a **rodada em andamento**, sinalizam que é **parcial**.
- **Configuração centralizada na planilha** (criada na 1ª execução, editável direto no Sheets; o app relê a cada ~2 min):
  - **`participantes`** — `Posição | Nome | Apelido | Senha` (o **apelido** é o que aparece no dash; a **senha** deixa aquele participante editar só o seu time).
  - **`confrontos`** — `Rodada | Casa 1 | Fora 1 | Casa 2 | Fora 2 | Casa 3 | Fora 3` (a tabela do turno; os confrontos da rodada atual são montados por ela).
  - **`config`** — `rodada_inicial`, `rodada_final` (range da classificação/histórico) e `senha_master`.
- **Acesso por senha (na barra lateral):** sem senha o app é **somente-leitura**; a **senha do participante** libera editar **apenas o time dele**; a **senha master** libera **editar todos os times** + as ações de admin. Cada participante escala pela sua senha e o placar/arquivamento seguem a tabela de confrontos.
- Persistência em Google Sheets (via secrets do Streamlit).

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
- **Google Sheets (opcional)** — copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml` e preencha `[gsheets]`/`[gcp_service_account]`. Sem esses secrets a escalação é salva apenas localmente (`escalacao_salva.json`, efêmero) e, sem planilha, não há senhas cadastradas: o app fica somente-leitura. As **senhas** (participantes e master) ficam na planilha, não nos secrets.

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

**Duas fases por rodada:**

1. **Mercado fechado (ao vivo):** o script **sobrescreve** a aba `rodada{N}` a cada execução com as parciais do momento (por time: jogador, posição, clube, parcial, scouts e `atleta_id`).
2. **Mercado reaberto (consolidação):** o Cartola continua ajustando scouts depois dos jogos (SG perdido, DS revisado etc.), então a última gravação ao vivo pode não ser a final. Com o mercado aberto, `/atletas/pontuados/{N}` devolve os scouts **fechados** da rodada N; o script confere a aba `rodada{N}` contra a API e reescreve **só as células divergentes** (Parcial, Scouts, TOTAL), marcando o título como **"consolidado"**. É idempotente e não depende do horário em que o cron roda. Usa os jogadores gravados na própria aba (`atleta_id`, com fallback por apelido+clube nas abas antigas) — nunca a aba de estado, que já pode ter a escalação da rodada seguinte.

Se sobrar alguma divergência que o robô não consiga corrigir sozinho (ex.: jogador não encontrado na API), o job **falha uma vez** e o GitHub manda e-mail; o título da aba registra a pendência.

**Checagem/correção manual:** `python checar_rodadas.py` confere todas as abas `rodada{N}` contra a API (só leitura; relatório em `checagem_rodadas.csv`). Com `--corrigir`, reescreve as divergências (salvando antes um backup local `backup_rodadas_<data>.json`). Usa o `.streamlit/secrets.toml` ou as variáveis `GCP_SERVICE_ACCOUNT`/`GSHEETS_KEY`.

Quem dispara é o workflow `.github/workflows/arquivar-rodada.yml` (de hora em hora), independente do app estar aberto. O workflow tem um passo de **keepalive** (o GitHub desativa agendamentos de repositórios públicos após 60 dias sem commits) e `concurrency` para nunca rodar duas gravações ao mesmo tempo. As escalações vêm da aba `estado` do Sheets — ou seja, **exige a persistência em Google Sheets ligada** no app.

Há também um botão **"Arquivar rodada agora"** na sidebar do app (aparece só para o **master** com o Sheets configurado), para arquivar sob demanda a rodada atual — convive com o robô automático (ambos gravam/atualizam a mesma aba `rodada{N}`).

**Configuração (uma vez):** em *GitHub → repositório → Settings → Secrets and variables → Actions*, crie:

| Secret | Valor |
|---|---|
| `GCP_SERVICE_ACCOUNT` | o **JSON inteiro** da conta de serviço (a mesma do app) |
| `GSHEETS_KEY` | o ID da planilha (da URL) |

Depois, em **Actions**, habilite os workflows. Dá para testar na hora em **Actions → Arquivar rodada → Run workflow** (fora de rodada encerrada, ele só loga "nada a fazer" — o esperado).

> Com a consolidação, atrasos do cron só atrasam a correção — não a impedem. Confira de vez em quando em **Actions** se o workflow está habilitado.

