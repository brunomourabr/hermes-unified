# CATALOGO DE FUNCIONALIDADES - Hermes Unified

> Seu assistente AI com 12 agentes, 16 bridges, e memoria persistente
> Tudo que o sistema pode fazer - organizado, honesto, e direto ao ponto

---

## COMO LER ESTE CATALOGO

Legenda de status:
- ✅ **Live no grafo** - Funcionalidade integrada ao LangGraph, use via main.py
- ⚡ **Disponivel como tool** - Bridge existe, pode ser chamada via codigo, mas nao esta no grafo principal
- 🔧 **Precisa de credenciais** - Bridge existe mas requer API key / token / service account

---

## 1. GERACAO DE CODIGO - MiMo Code

### Gerar codigo a partir de especificacao
✅ Live no grafo | Entrada: descricao textual | Saida: arquivo .py
> Cria scripts Python completos a partir de uma descricao em linguagem natural.
```
Comando: python main.py "Crie uma API Flask com CRUD de usuarios"
```

### Refatorar codigo existente
✅ Live no grafo | Entrada: arquivo .py + instrucoes | Saida: arquivo refatorado
> Modifica codigo existente seguindo instrucoes, com backup automatico.
```
Comando: python main.py "Refatore este codigo para usar async/await" --files meu_arquivo.py
```

### Validar sintaxe Python
⚡ Disponivel como tool | Entrada: arquivo .py | Saida: valido/invalido
> Verifica se o codigo gerado tem sintaxe Python correta.

### Executar testes no codigo
⚡ Disponivel como tool | Entrada: arquivo .py | Saida: resultado de testes
> Executa testes automaticos no codigo gerado.

---

## 2. PESQUISA E SCRAPING - Web, Scraper, ScraperFallback

### Pesquisa na internet
✅ Live no grafo | Entrada: pergunta | Saida: links + descricoes
> Busca informacoes atualizadas na web automaticamente.
```
Comando: python main.py "Pesquise as ultimas noticias sobre IA no Brasil"
```

### Scraping de site especifico
✅ Live no grafo | Entrada: URL | Saida: texto markdown
> Extrai o conteudo completo de qualquer pagina web.
```
Comando: python main.py "Extraia o conteudo de https://exemplo.com"
```

### Busca + Scrape automatico
✅ Live no grafo | Entrada: termo de busca | Saida: texto do primeiro resultado
> Pesquisa na web e ja extrai o conteudo do primeiro resultado.

### Extracao de tabelas HTML
⚡ Disponivel como tool | Entrada: URL | Saida: dados estruturados JSON
> Converte tabelas HTML em dados JSON organizados.

### Extracao de links de pagina
⚡ Disponivel como tool | Entrada: URL | Saida: lista de links
> Extrai todos os links de uma pagina, com filtro opcional por padrao.

### Scraping fallback (HTTP direto)
⚡ Disponivel como tool | Entrada: URL | Saida: texto limpo
> Alternativa quando Firecrawl falha - usa requests + BeautifulSoup.

### Batch Scraping
⚡ Disponivel como tool | Entrada: lista de URLs | Saida: dicionario de conteudos
> Scrape multiplas URLs de uma vez (sequencial).

---

## 3. DOCUMENTOS E CONHECIMENTO - Knowledge, Reporter, Sheets

### Extracao de conhecimento de PDF
✅ Live no grafo | Entrada: PDF + pergunta | Saida: grafo de conhecimento
> Extrai conceitos, relacoes e entidades de documentos PDF como grafos.
```
Comando: python main.py "Extraia os conceitos principais deste PDF" --files documento.pdf
```

### Consulta ao grafo de conhecimento
✅ Live no grafo | Entrada: pergunta | Saida: resultados semanticos
> Busca informacoes no conhecimento extraido anteriormente.

### Chat com documento
⚡ Disponivel como tool | Entrada: pergunta | Saida: resposta contextual
> Conversa diretamente com o conteudo extraido de documentos.

### Relatorio PDF profissional
✅ Live no grafo | Entrada: resumo + secoes | Saida: PDF com capa + sumario
> Gera relatorios PDF com capa escura, sumario, secoes numeradas e paginacao.
```
Comando: python main.py "Gere um relatorio sobre os resultados da pesquisa"
```

### Relatorio HTML interativo
✅ Live no grafo | Entrada: conteudo | Saida: HTML responsivo
> Versao web do relatorio com navegacao entre secoes.

### Planilha local (JSON + CSV)
✅ Live no grafo | Entrada: titulo + cabecalhos | Saida: arquivos .json e .csv
> Cria planilhas organizadas mesmo sem Google Sheets configurado.
```
Comando: python main.py "Crie uma planilha de precos com colunas Produto, Valor, Data"
```

### Planilha Google Sheets
🔧 Online com credenciais | Entrada: titulo + dados | Saida: URL do Google Sheet
> Cria planilhas reais no Google Sheets (requer service account).

### Leitura de planilha
✅ Live no grafo | Entrada: caminho/ID | Saida: dados em JSON
> Le planilhas locais ou Google Sheets.

### Exportacao CSV
⚡ Disponivel como tool | Entrada: sheet ID/path | Saida: arquivo .csv
> Exporta qualquer planilha para formato CSV padrao.

---

## 4. VISUALIZACAO E APRESENTACAO - Viz

### Grafico de barras
✅ Live no grafo | Entrada: categorias + valores | Saida: PNG
> Grafico de barras colorido com labels e valores.
```
Comando: python main.py "Crie um grafico de barras comparando vendas por mes"
```

### Grafico de linhas
✅ Live no grafo | Entrada: x + y | Saida: PNG
> Grafico de linha com marcadores e grid.
```
Comando: python main.py "Mostre a tendencia de crescimento dos ultimos 6 meses"
```

### Grafico de pizza
✅ Live no grafo | Entrada: labels + valores | Saida: PNG
> Grafico de pizza com percentuais automaticos.
```
Comando: python main.py "Crie um grafico de pizza com a proporcao de vendas por categoria"
```

### Grafico de dispersao
✅ Live no grafo | Entrada: x + y | Saida: PNG
> Scatter plot para correlacao entre variaveis.

### Grafico interativo Plotly
⚡ Disponivel como tool | Entrada: dados | Saida: HTML interativo
> Graficos que permitem zoom, hover, e interacao.

### Dashboard HTML multiplos graficos
✅ Live no grafo | Entrada: lista de graficos | Saida: HTML
> Pagina web com todos os graficos gerados em uma unica visualizacao.

### Apresentacao PowerPoint
⚡ Disponivel como tool | Entrada: graficos + titulo | Saida: .pptx
> Apresentacao profissional com slides para cada grafico.

### Apresentacao PowerPoint 42c
⚡ Disponivel como tool | Entrada: slides + conteudo | Saida: .pptx
> Apresentacao com branding 42c - capa escura, destaques vermelhos, fontes profissionais.

### Grafico de comparacao
✅ Live no grafo | Entrada: multiplos datasets | Saida: PNG
> Compara duas ou mais series de dados no mesmo grafico.
```
Comando: python main.py "Compare vendas de 2024 vs 2025 em um grafico"
```

---

## 5. MONITORAMENTO - Observer, Notifier

### Watcher de preco web
✅ Live no grafo | Entrada: URL + intervalo | Saida: script watcher
> Cria um monitor que verifica precos em paginas web periodicamente.
```
Comando: python main.py "Monitore o preco deste produto a cada 1h: https://loja.com/produto"
```

### Watcher de conteudo web
✅ Live no grafo | Entrada: URL + intervalo | Saida: script watcher
> Detecta mudancas no conteudo de uma pagina web (por hash MD5).
```
Comando: python main.py "Crie um watcher diario para detectar mudancas em https://site.com"
```

### Watcher de modificacao de arquivo
✅ Live no grafo | Entrada: caminho do arquivo | Saida: script watcher
> Monitora alteracoes em arquivos locais (tamanho, data de modificacao).
```
Comando: python main.py "Monitore alteracoes no arquivo /etc/config.json a cada 30m"
```

### Watcher de health check de API
✅ Live no grafo | Entrada: URL da API | Saida: script watcher
> Verifica se endpoints de API estao respondendo (status code, tempo de resposta).
```
Comando: python main.py "Verifique a saude da API https://api.exemplo.com/health diariamente"
```

### Instalacao de watcher no crontab
⚡ Disponivel como tool | Entrada: nome do watcher | Saida: cron ativado
> Instala automaticamente o watcher no crontab do sistema.

### Listagem de watchers ativos
✅ Live no grafo | Entrada: comando | Saida: lista de watchers
> Mostra todos os watchers criados e seus status.

### Notificacao de conclusao de tarefa
✅ Live no grafo | Entrada: resultado da tarefa | Saida: notificacao
> Envia notificacao quando uma tarefa e concluida.

### Notificacao de erro
⚡ Disponivel como tool | Entrada: erro | Saida: alerta
> Notifica quando um agente encontra um erro.

### Notificacao Telegram
🔧 Online com credenciais | Entrada: mensagem | Saida: Telegram
> Envia notificacoes para o Telegram (requer bot token).

---

## 6. ANALISE DE MIDIA - DV360, TikTok, Campaign Tracker

### Listar anunciantes DV360
✅ Live no grafo | Entrada: comando | Saida: lista de anunciantes
> Lista todas as contas de anunciantes no Google Display & Video 360.
```
Comando: python main.py "Liste os anunciantes no DV360"
```

### Performance de campanhas DV360
✅ Live no grafo | Entrada: advertiser ID | Saida: relatorio JSON
> Metricas de performance: impressoes, clicks, gasto, conversoes.
```
Comando: python main.py "Mostre a performance do advertiser 123456 de 2024-01-01 a 2024-12-31"
```

### Comparacao de periodos DV360
✅ Live no grafo | Entrada: advertiser ID + datas | Saida: comparativo
> Compara performance entre dois periodos com calculo de delta percentual.

### Listar anunciantes TikTok
✅ Live no grafo | Entrada: comando | Saida: lista de anunciantes
> Lista contas de anunciantes no TikTok Ads.
```
Comando: python main.py "Liste as contas de anunciantes do TikTok"
```

### Performance de campanhas TikTok
✅ Live no grafo | Entrada: advertiser ID | Saida: JSON
> Metricas de campanhas TikTok: impressoes, clicks, CTR, gasto.
```
Comando: python main.py "Mostre as campanhas TikTok do advertiser 123456"
```

### Estatisticas de Ad Groups TikTok
✅ Live no grafo | Entrada: advertiser ID | Saida: JSON
> Performance por grupo de anuncio com detalhes de targeting.
```
Comando: python main.py "Mostre os ad groups TikTok do advertiser 123456"
```

### Relatorio TikTok completo
✅ Live no grafo | Entrada: advertiser ID | Saida: JSON
> Relatorio agregado de campanhas + ad groups com recomendacoes.

### Scaffold Google Ads
⚡ Scaffold code | Entrada: customer ID | Saida: instrucoes de setup
> Placeholder para integracao com Google Ads (requer google-ads lib).

### Scaffold Meta Ads
⚡ Scaffold code | Entrada: ad account ID | Saida: instrucoes de setup
> Placeholder para integracao com Meta Ads (requer facebook-business lib).

---

## 7. MIDIAS SOCIAIS - Social Publisher

### Postar texto no X/Twitter
✅ Live no grafo | Entrada: texto | Saida: tweet ou outbox
> Publica posts no X/Twitter ou salva em outbox local.
```
Comando: python main.py "Publique no Twitter: Acabamos de lancar o Hermes Unified v2!"
```

### Postar com imagem
✅ Live no grafo | Entrada: texto + imagem | Saida: tweet com midia
> Post com imagem anexada.

### Postar thread
✅ Live no grafo | Entrada: lista de textos | Saida: thread de tweets
> Sequencia de tweets encadeados.

### Listar posts pendentes (outbox)
⚡ Disponivel como tool | Entrada: comando | Saida: lista de posts
> Mostra posts aguardando publicacao no outbox local.

### Listar posts enviados
⚡ Disponivel como tool | Entrada: comando | Saida: historico
> Historico de posts ja publicados.

---

## 8. VISAO COMPUTACIONAL - Vision Scout, Hermes Bridge

### Analise geral de imagem
✅ Live no grafo | Entrada: caminho da imagem | Saida: descricao detalhada
> Descreve o conteudo de uma imagem usando IA multimodal.
```
Comando: python main.py "Analise esta imagem" --files foto.png
```

### Extracao de texto de imagem (OCR via IA)
✅ Live no grafo | Entrada: imagem com texto | Saida: texto extraido
> Le e extrai textos visiveis em imagens.
```
Comando: python main.py "Extraia o texto desta imagem" --files documento_escaneado.png
```

### Comparacao de imagens
✅ Live no grafo | Entrada: duas imagens | Saida: comparacao textual
> Compara duas imagens e descreve similaridades e diferencas.
```
Comando: python main.py "Compare estas duas imagens" --files imagem1.png imagem2.png
```

### Analise de screenshot
✅ Live no grafo | Entrada: screenshot + elementos de interesse | Saida: analise focada
> Analisa capturas de tela focando em elementos especificos (textos, precos, botoes).
```
Comando: python main.py "Analise esta screenshot focando em precos e botoes" --files print_tela.png
```

---

## 9. MEMORIA E AUTOMACAO - Memory Bridge, Cron Jobs

### Memoria persistente entre execucoes
✅ Sempre ativo | 4 tabelas SQLite
> Toda execucao e salva automaticamente no banco de memoria.
```
Comando: (automatico - toda execucao salva sessoes e artefatos)
```

### Busca de sessoes anteriores
⚡ Disponivel como tool | Entrada: termo de busca | Saida: sessoes passadas
> Consulta execucoes anteriores pelo objetivo.

### Cache de conhecimento com TTL
⚡ Disponivel como tool | Entrada: chave + valor + horas | Saida: cache salvo
> Armazena informacoes temporariamente com expiracao automatica.

### Observacoes de watchers
⚡ Disponivel como tool | Entrada: nome do watcher | Saida: historico
> Recupera observacoes coletadas pelos watchers automaticamente.

### Estatisticas do banco de memoria
⚡ Disponivel como tool | Entrada: comando | Saida: contagens por tabela
> Mostra quantas sessoes, artefatos, observacoes e cache existem.

### Automacao via Cron
⚡ Disponivel como tool | Scripts Python executaveis
> Watchers sao scripts Python autonomos que rodam via cron.
```
No crontab: */60 * * * * python3 /opt/projetos/hermes-unified/output/observations/scripts/watcher_preco_amazon.py
```

---

## 10. INTEGRACOES - Hermes Bridge

### Notificacao Telegram
🔧 Online com credenciais | Entrada: mensagem | Saida: Telegram
> Envia mensagens formatadas para canais Telegram.
```
Requer: TELEGRAM_BOT_TOKEN e TELEGRAM_HOME_CHANNEL
```

### Visao multimodal via OpenRouter
🔧 Online com credenciais | Entrada: imagem + pergunta | Saida: analise
> Usa Gemini 3 Flash da Google para analise de imagens.
```
Requer: OPENROUTER_API_KEY
```

### Agregacao de resultados
✅ Live no grafo | Integrator node
> Consolida outputs de multiplos agentes em um resultado unico.

---

## 11. INFRAESTRUTURA - Config, Secrets, Output

### Gerenciamento de chaves via secrets.json
✅ Funcional | Arquivo: config/secrets.json
> Todas as API keys em um lugar, protegido com chmod 600.

### Fallback para variaveis de ambiente
✅ Funcional | Fallback automatico
> Se nao encontrar em secrets.json, busca em environment variables.

### Saida organizada por tipo
✅ Funcional | 11 diretorios de output
> Cada bridge salva em seu proprio diretorio (viz/, reports/, sheets/, etc.).

### CLI via main.py
✅ Funcional | Entrada: objetivo + arquivos
> Interface de linha de comando simples e direta.
```
Uso: python main.py "<objetivo>" [--files arquivo1 arquivo2 ...]
```

### Resultado salvo em JSON
✅ Funcional | Arquivo: /tmp/hermes_unified_result_*.json
> Toda execucao salva resultado completo em JSON para consulta posterior.

---

## GUIA RAPIDO - Quick Start

### 1. Configuracao inicial minima

```bash
# Apenas para classificacao de tarefas (funciona sem, mas melhor com)
export DEEPSEEK_API_KEY="sua_chave_aqui"

# Opcional, mas recomendado
export OPENROUTER_API_KEY="sua_chave_aqui"
export FIRECRAWL_API_KEY="sua_chave_aqui"
```

Ou crie `config/secrets.json`:
```json
{
  "DEEPSEEK_API_KEY": "sk-...",
  "OPENROUTER_API_KEY": "sk-...",
  "FIRECRAWL_API_KEY": "fc-..."
}
```

### 2. Teste rapido

```bash
cd /opt/projetos/hermes-unified

# Ver se esta tudo ok
python3 -c "from core.graph import build_master_graph; print('Grafo compilado com sucesso!')"

# Gerar codigo
python3 main.py "Crie uma calculadora em Python com interface Tkinter"

# Pesquisar na web
python3 main.py "Quais sao as ultimas inovacoes em IA generativa?"

# Extrair conhecimento de PDF
python3 main.py "Extraia os conceitos principais deste documento" --files relatorio.pdf

# Criar visualizacao
python3 main.py "Crie um grafico de barras mostrando vendas por mes"

# Criar relatorio
python3 main.py "Gere um relatorio com os resultados encontrados"

# Monitorar preco
python3 main.py "Monitore o preco do iPhone na Amazon a cada 1h"

# Analisar imagem
python3 main.py "Analise esta imagem em detalhes" --files screenshot.png
```

### 3. Exemplo completo - Pipeline de pesquisa + relatorio

```bash
# Passo 1: Pesquisar sobre um topico
python main.py "Pesquise sobre energia solar no Brasil em 2026"

# Passo 2: O resultado vai para o contexto automaticamente.
# O grafo detecta que ja tem dados e cria visualizacao + relatorio.
```

### 4. Para desenvolvedores

```python
from core.graph import run_agent

# Executa qualquer tarefa programaticamente
resultado = run_agent(
    "Crie um script que baixa dados de uma API e salva em CSV",
    input_files=["spec.pdf"]  # opcional
)

print(resultado["success"])      # True/False
print(resultado["artifacts"])    # lista de artefatos gerados
print(resultado["context"])      # contexto completo
```

### 5. Bridges disponiveis programaticamente

```python
from tools.viz_bridge import get_viz_bridge
viz = get_viz_bridge()
path, ok, msg = viz.generate_chart(
    {"labels": ["Jan", "Fev", "Mar"], "values": [100, 200, 150]},
    "bar", "Vendas 2026"
)
print(f"Grafico salvo em: {path}")

from tools.memory_bridge import get_memory_bridge
mem = get_memory_bridge()
print(mem.stats())  # estatisticas do banco de memoria
```

---

## RESUMO - O que o Hermes Unified FAZ e NAO FAZ

### FAZ ✅
- Gera codigo Python funcional
- Pesquisa e extrai conteudo da web
- Extrai conhecimento de PDFs como grafos
- Cria graficos e dashboards (PNG, HTML, Plotly)
- Gera apresentacoes PowerPoint profissionais
- Cria relatorios PDF e HTML
- Monitora precos, conteudo web, arquivos e APIs
- Analisa imagens com IA multimodal
- Publica posts no X/Twitter (ou salva outbox)
- Cria planilhas locais e Google Sheets
- Analisa campanhas DV360 e TikTok (dados mock)
- Memoriza execucoes entre sessoes
- Notifica por Telegram (se configurado)

### NAO FAZ (ainda) ❌
- Google Ads e Meta Ads reais (scaffold apenas)
- Video processing
- OCR real (usa modelo de visao generico)
- Streaming de responses
- Interface web (apenas CLI)
- Deploy automatico de codigo gerado
- Autenticacao multi-usuario
- Processamento paralelo de tarefas

---

*Hermes Unified v2 - Construido com LangGraph 1.2.6, 12 agentes, 16 bridges*
*Documentacao gerada em 29/06/2026*
