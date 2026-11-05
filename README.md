# jurisprudencia-tse

Servidor [MCP](https://modelcontextprotocol.io) para pesquisar a jurisprudência do Tribunal Superior
Eleitoral pelo Claude, com dados direto do portal oficial
([jurisprudencia.tse.jus.br](https://jurisprudencia.tse.jus.br/#/jurisprudencia/pesquisa)).

Projeto independente, sem vínculo com o TSE.

## O que faz

| Ferramenta | Para quê |
|---|---|
| `tse_pesquisar` | Pesquisa avançada completa: texto livre (com inteiro teor e sinônimos), número, relatores, classes, eleições, ementa/decisão, partes, UF, datas de julgamento ou publicação, legislação (lei, artigo, parágrafo, inciso, alínea), tipo de decisão, ordenação e paginação. |
| `tse_obter_decisao` | Ementa e decisão completas, partes, legislação, súmulas, precedentes e decisões relacionadas. |
| `tse_inteiro_teor` | Baixa o PDF do acórdão e devolve o texto, em trechos. |
| `tse_citacao` | Citação ABNT no formato do botão "Copiar citação" do portal (sem o HTML que o portal deixa vazar), cabeçalho de referência, link da decisão e do andamento processual. |
| `tse_listar_valores` | Valores válidos para os filtros: classes, relatores, anos de eleição e normas. |

## Como funciona e por que usa um navegador

O portal exige um token **hCaptcha** em cada pesquisa. Este MCP não contorna o captcha: ele abre o
portal no Edge (ou Chrome), muda o endereço da página para a pesquisa pedida e lê a resposta que o
próprio portal recebe. O captcha roda como numa pesquisa manual.

A janela do navegador fica **minimizada**. Na maior parte das vezes o hCaptcha valida sozinho, sem
aparecer. Quando ele exige um desafio ("selecione as imagens…"), a janela vem para a frente e a
ferramenta responde **CAPTCHA PENDENTE**: resolva o desafio e peça ao Claude para repetir a
pesquisa. A página é recarregada e a janela volta a minimizar.

Navegador sem janela (headless) não é opção: o portal bloqueia esse tipo de acesso com HTTP 403.

Inteiro teor, listas de valores e citação não passam pelo captcha: usam chamadas HTTP diretas aos
mesmos endereços que o portal usa.

Detalhes técnicos do portal (endpoints, campos, formato das respostas, comportamento do captcha):
[docs/MAPEAMENTO_API_PORTAL_TSE.md](docs/MAPEAMENTO_API_PORTAL_TSE.md).

## Requisitos

- Windows 10 ou 11 (macOS e Linux também funcionam)
- Microsoft Edge (já vem no Windows) ou Google Chrome
- [uv](https://docs.astral.sh/uv/), o instalador usado abaixo. Ele baixa sozinho um Python
  compatível (3.11 ou mais recente) se não houver um no computador.
- Git (o uv usa para baixar o código do GitHub): [git-scm.com](https://git-scm.com/download/win)

Não é preciso baixar navegador do Playwright: o MCP usa o Edge/Chrome já instalado, com um perfil
próprio, separado do seu.

## Instalação

São três passos, feitos uma vez em cada computador.

**1. Instale o uv.** No PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Feche e abra o PowerShell de novo, para ele reconhecer o comando `uv`.

**2. Instale o MCP:**

```powershell
uv tool install git+https://github.com/luisguilhermeverissimo-hue/jurisprudencia-tse
```

Isso cria o comando `jurisprudencia-tse` em `%USERPROFILE%\.local\bin`.

**3. Ligue o MCP ao Claude** (Claude Code, Claude Desktop ou os dois), conforme abaixo.

### Claude Code

```powershell
claude mcp add --scope user jurisprudencia-tse -- jurisprudencia-tse
```

`--scope user` deixa o MCP disponível em todas as pastas. Confira com `claude mcp list`.

### Claude Desktop

No Claude Desktop, abra **Configurações › Desenvolvedor › Editar configuração**. Isso abre o
arquivo `%APPDATA%\Claude\claude_desktop_config.json`. Acrescente dentro de `"mcpServers"`
(crie a chave se ela não existir):

```json
{
  "mcpServers": {
    "jurisprudencia-tse": {
      "command": "jurisprudencia-tse"
    }
  }
}
```

Feche o Claude Desktop pela bandeja do sistema (não só a janela) e abra de novo.

Se o Claude Desktop não achar o comando, use o caminho completo:
`"command": "C:\\Users\\SEU_USUARIO\\.local\\bin\\jurisprudencia-tse.exe"`.

### Atualizar e desinstalar

```powershell
uv tool upgrade jurisprudencia-tse
```

Depois de atualizar, reinicie o Claude. Para remover: `uv tool uninstall jurisprudencia-tse` e
`claude mcp remove --scope user jurisprudencia-tse`. O cache fica em
`%LOCALAPPDATA%\jurisprudencia-tse` e pode ser apagado à mão.

### Sem instalar (uvx)

Para experimentar sem instalar, o Claude pode rodar direto do GitHub. A primeira execução demora,
porque baixa as dependências:

```powershell
claude mcp add --scope user jurisprudencia-tse -- uvx --from git+https://github.com/luisguilhermeverissimo-hue/jurisprudencia-tse jurisprudencia-tse
```

## Configuração opcional

| Variável | Padrão | Uso |
|---|---|---|
| `TSE_NAVEGADOR` | `msedge` | `msedge` ou `chrome` |
| `TSE_JANELA` | `minimizada` | `minimizada` ou `visivel` (janela sempre à vista) |
| `TSE_PASTA_DADOS` | `%LOCALAPPDATA%\jurisprudencia-tse` | Cache de decisões, PDFs e perfil do navegador |
| `TSE_PASTA_INTEIRO_TEOR` | `<dados>\inteiro-teor` | Onde salvar os PDFs |
| `TSE_INTERVALO_DOWNLOADS` | `10` | Segundos mínimos entre downloads de PDF |
| `TSE_TEMPO_MAXIMO_PESQUISA` | `40` | Segundos de espera pela resposta da pesquisa |

No Claude Code, passe as variáveis com `-e`, por exemplo
`claude mcp add --scope user -e TSE_JANELA=visivel jurisprudencia-tse -- jurisprudencia-tse`.
No Claude Desktop, use a chave `"env": { "TSE_JANELA": "visivel" }` ao lado de `"command"`.

## Exemplos de pedidos ao Claude

- "Pesquise no TSE acórdãos de 2024 e 2025 sobre abuso de poder econômico em REspEl, com art. 22 da LC 64/90."
- "Traga a ementa completa e a citação da segunda decisão."
- "Leia o inteiro teor e resuma como o relator tratou a gravidade."
- "Quais relatores mais julgaram propaganda antecipada desde 2022?" (use a distribuição dos resultados)

## Limites e uso responsável

- Cada página de resultados passa pelo hCaptcha. Prefira páginas maiores e filtros precisos a
  paginar muito; pesquisas em volume aumentam a chance de desafios.
- O servidor de inteiro teor recusa downloads seguidos. O MCP espaça as chamadas e guarda os PDFs
  em cache.
- O portal não pagina além de 10.000 resultados.
- Confira sempre a decisão no portal oficial antes de citá-la em peça.

## Desenvolvimento

```powershell
git clone https://github.com/luisguilhermeverissimo-hue/jurisprudencia-tse.git
cd jurisprudencia-tse
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest
.venv\Scripts\python scripts\testar_mcp.py   # ponta a ponta: abre o navegador e chama cada ferramenta
```

Para o Claude usar a cópia em desenvolvimento, aponte o MCP para o Python do `.venv`:
`claude mcp add --scope user jurisprudencia-tse -- C:\caminho\para\jurisprudencia-tse\.venv\Scripts\python.exe -m jurisprudencia_tse`.

## Licença

[MIT](LICENSE).
