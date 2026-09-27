# Radar das Seis — by Enzo Monteiro

Classificação, jogos e estatísticas do Brasileirão, Premier League, La Liga, Serie A, Bundesliga e Ligue 1.
O site se atualiza sozinho: a cada 30 minutos um robô do GitHub busca os jogos encerrados no
[football-data.org](https://www.football-data.org), recalcula tudo e publica de novo.

## O que tem na pasta

| Arquivo | Para que serve |
| --- | --- |
| `index.html` | O site inteiro (visual, escudos e cálculos). |
| `data.json` | Os dados das ligas. O robô reescreve este arquivo quando termina uma partida. |
| `update_data.py` | O script que busca os dados na API. |
| `.github/workflows/atualizar.yml` | O agendamento que roda o script e publica o site. |

## Colocando no ar (uns 10 minutos, dá para fazer pelo iPad)

1. **Chave da API.** Cadastre-se grátis em https://www.football-data.org/client/register. A chave chega por e-mail.
2. **Conta no GitHub.** Crie em https://github.com/signup, se ainda não tiver.
3. **Repositório.** Clique em **New repository**, dê o nome `radar-das-seis`, marque **Public** e crie.
4. **Arquivos.** No repositório, toque em **Add file → Upload files** e envie `index.html`, `data.json`,
   `update_data.py` e `README.md`. Toque em **Commit changes**.
5. **Guardar a chave.** Vá em **Settings → Secrets and variables → Actions → New repository secret**.
   Nome: `FOOTBALL_DATA_TOKEN`. Valor: a chave do passo 1.
6. **Ativar o site.** Em **Settings → Pages**, no campo **Source**, escolha **GitHub Actions**.
7. **Agendamento.** Volte para a página inicial do repositório, toque em **Add file → Create new file**,
   digite o nome `.github/workflows/atualizar.yml` (as barras criam as pastas sozinhas), cole o conteúdo
   do arquivo `atualizar.yml` desta pasta e toque em **Commit changes**.
8. **Primeira atualização.** Abra a aba **Actions**, escolha **Atualizar e publicar** e toque em
   **Run workflow**. Em 2 ou 3 minutos o site estará em
   `https://SEU-USUARIO.github.io/radar-das-seis/`.

Depois disso não precisa fazer mais nada: o robô roda sozinho a cada 30 minutos e só publica quando
algum jogo terminou.

## Bom saber

- **Atraso:** o GitHub às vezes atrasa o agendamento em alguns minutos. Um jogo encerrado costuma
  aparecer no site entre 30 e 60 minutos depois do apito final.
- **Pausa automática:** se o repositório ficar 60 dias sem nenhuma atividade, o GitHub pausa o
  agendamento. Na aba **Actions**, é só tocar em **Enable workflow** para voltar.
- **Plano gratuito do football-data.org:** traz resultados, placar do intervalo, tabela e artilharia
  (com jogos, gols, assistências e pênaltis). Cartões, escalações e estatísticas de jogo
  (finalizações, posse, xG) exigem plano pago do football-data.org ou outra API, como a API-Football.
- **Times promovidos:** clubes novos na próxima temporada entram sozinhos, com o escudo da própria API.
- **Rodar manualmente no computador:** `FOOTBALL_DATA_TOKEN=sua_chave python3 update_data.py`
