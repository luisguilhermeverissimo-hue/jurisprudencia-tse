# jurisprudencia-tse

Servidor [MCP](https://modelcontextprotocol.io) para pesquisar a jurisprudência da Justiça Eleitoral
pelo Claude, com dados direto dos portais oficiais: o do Tribunal Superior Eleitoral
([jurisprudencia.tse.jus.br](https://jurisprudencia.tse.jus.br/#/jurisprudencia/pesquisa)) e o
unificado dos 27 Tribunais Regionais Eleitorais
([jurisprudencia-tres.tse.jus.br](https://jurisprudencia-tres.tse.jus.br/#/jurisprudencia/pesquisa)).

Projeto independente, sem vínculo com o TSE ou com os TREs.

## O que faz

| Ferramenta | Para quê |
|---|---|
| `tse_pesquisar` | Pesquisa avançada completa no TSE ou nos TREs (um, vários ou todos): texto livre (com inteiro teor e sinônimos), número, relatores, classes, eleições, ementa/decisão, partes, UF, município, datas de julgamento ou publicação, legislação (lei, artigo, parágrafo, inciso, alínea), tipo de decisão, ordenação e paginação. |
| `tse_obter_decisao` | Ementa e decisão completas, partes, legislação, súmulas, precedentes e decisões relacionadas. |
| `tse_inteiro_teor` | Baixa o PDF do acórdão e devolve o texto, em trechos. |
| `tse_citacao` | Citação ABNT no formato do botão "Copiar citação" do portal (sem o HTML que o portal deixa vazar), cabeçalho de referência, link da decisão e do andamento processual. |
| `tse_listar_valores` | Valores válidos para os filtros: classes, relatores, anos de eleição e normas, do TSE, de um TRE ou de todos os TREs. |

Os nomes começam com `tse_` porque os dois portais são do sistema do TSE; todas as ferramentas
valem para o TSE e para os TREs. Na pesquisa, o padrão é o TSE: para os TREs, peça ao Claude
("pesquise no TRE-PE…", "nos TREs do Nordeste…", "em todos os TREs…").

TSE e TREs ficam em portais separados, então uma mesma pesquisa vale para um ou para o outro.
Para comparar, o Claude faz uma pesquisa em cada.

## Como funciona e por que usa um navegador

Os portais exigem um token **hCaptcha** em cada pesquisa. Este MCP não contorna o captcha: ele abre o
portal no Edge (ou Chrome), numa aba para o TSE e outra para os TREs, muda o endereço da página para a pesquisa pedida e lê a resposta que o
próprio portal recebe. O captcha roda como numa pesquisa manual.

A janela do navegador fica **escondida**: fora da área visível da tela e fora da barra de tarefas.
Continua sendo um Edge comum, com janela, como o portal espera; você só não a vê. Na maior parte
das vezes o hCaptcha valida sozinho, sem aparecer. Quando ele exige um desafio ("selecione as imagens…"), a janela vem para o centro da tela e a
ferramenta responde **CAPTCHA PENDENTE**: resolva o desafio e peça ao Claude para repetir a
pesquisa. A página é recarregada e a janela volta a se esconder.

Navegador sem janela (headless) não é opção: o portal bloqueia esse tipo de acesso com HTTP 403.

Inteiro teor, listas de valores e citação não passam pelo captcha: usam chamadas HTTP diretas aos
mesmos endereços que o portal usa.

Detalhes técnicos do portal (endpoints, campos, formato das respostas, comportamento do captcha):
[docs/MAPEAMENTO_API_PORTAL_TSE.md](docs/MAPEAMENTO_API_PORTAL_TSE.md).

## Requisitos

- Windows 10 ou 11 (macOS e Linux também funcionam)
- Microsoft Edge (já vem no Windows) ou Google Chrome
- Para a extensão do Claude Desktop, só isso. Para o Claude Code, também o
  [uv](https://docs.astral.sh/uv/), que baixa sozinho um Python compatível (3.11 ou mais recente).

Não é preciso baixar navegador do Playwright: o MCP usa o Edge/Chrome já instalado, com um perfil
próprio, separado do seu.

## Atualização automática

Instala-se uma vez só. A cada vez que o Claude abre, o MCP confere no GitHub qual é a versão mais
recente publicada e passa a usá-la: ninguém precisa baixar arquivo nem rodar comando para
atualizar. A primeira abertura depois de uma versão nova leva cerca de um minuto, porque prepara o
ambiente; as seguintes levam alguns segundos. Sem internet, roda a última versão já usada no
computador.

Uma versão nova só chega aos usuários quando é publicada como *release* no GitHub (veja
*Publicar uma versão nova*); alterações comuns no repositório não afetam ninguém.

No Claude Code, dá para fixar uma versão (por exemplo, voltar a uma anterior) com a variável
`TSE_VERSAO`, como `v0.3.0` (veja *Configuração opcional*).

## Instalação

### Claude Desktop, com um clique

1. Baixe a extensão:
   [jurisprudencia-tse.mcpb](https://github.com/luisguilhermeverissimo-hue/jurisprudencia-tse/releases/latest/download/jurisprudencia-tse.mcpb).
2. Dê dois cliques no arquivo baixado (ou arraste-o para a janela do Claude Desktop) e confirme
   **Instalar**.

Não é preciso instalar Python nem nada mais: o Claude Desktop baixa o que falta na primeira vez
em que a extensão roda, o que pode levar um minuto. Nas configurações da extensão dá para trocar
o navegador (Edge ou Chrome) e manter a janela visível.

Quem instalou uma versão anterior à 0.3.0 precisa instalar este arquivo uma última vez; a partir
dele, as atualizações chegam sozinhas.

### Claude Code

**1. Instale o uv** (uma vez). No PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Feche e abra o PowerShell de novo, para ele reconhecer o comando `uv`.

**2. Ligue o MCP ao Claude Code:**

```powershell
claude mcp add --scope user jurisprudencia-tse -- uv run https://raw.githubusercontent.com/luisguilhermeverissimo-hue/jurisprudencia-tse/main/mcpb/lancador.py
```

`--scope user` deixa o MCP disponível em todas as pastas. Confira com `claude mcp list`.

Para remover: `claude mcp remove --scope user jurisprudencia-tse`. O cache fica em
`%LOCALAPPDATA%\jurisprudencia-tse` e pode ser apagado à mão.

#### Versão fixa, sem atualização automática

Quem preferir instalar uma versão e atualizar à mão (exige Git):

```powershell
uv tool install git+https://github.com/luisguilhermeverissimo-hue/jurisprudencia-tse
claude mcp add --scope user jurisprudencia-tse -- jurisprudencia-tse
```

Para atualizar: `uv tool upgrade jurisprudencia-tse`. No Claude Desktop sem a extensão, o mesmo
comando vai em **Configurações › Desenvolvedor › Editar configuração**, dentro de `"mcpServers"`:
`"jurisprudencia-tse": { "command": "jurisprudencia-tse" }`.

## Configuração opcional

| Variável | Padrão | Uso |
|---|---|---|
| `TSE_NAVEGADOR` | `msedge` | `msedge` ou `chrome` |
| `TSE_VERSAO` | (a mais recente) | Fixa uma versão publicada, ex.: `v0.3.0` (lançador do Claude Code). |
| `TSE_JANELA` | `oculta` | `oculta` (fora da tela), `minimizada` (com ícone na barra de tarefas) ou `visivel` (sempre à vista) |
| `TSE_PASTA_DADOS` | `%LOCALAPPDATA%\jurisprudencia-tse` | Cache de decisões, PDFs e perfil do navegador |
| `TSE_PASTA_INTEIRO_TEOR` | `<dados>\inteiro-teor` | Onde salvar os PDFs |
| `TSE_INTERVALO_DOWNLOADS` | `10` | Segundos mínimos entre downloads de PDF |
| `TSE_TEMPO_MAXIMO_PESQUISA` | `40` | Segundos de espera pela resposta da pesquisa |

No Claude Code, passe as variáveis com `-e` antes do nome, por exemplo
`claude mcp add --scope user -e TSE_JANELA=visivel jurisprudencia-tse -- uv run https://raw.githubusercontent.com/luisguilhermeverissimo-hue/jurisprudencia-tse/main/mcpb/lancador.py`.
Na extensão do Claude Desktop, navegador e janela visível ficam nas configurações da extensão.

## Exemplos de pedidos ao Claude

- "Pesquise no TSE acórdãos de 2024 e 2025 sobre abuso de poder econômico em REspEl, com art. 22 da LC 64/90."
- "Traga a ementa completa e a citação da segunda decisão."
- "Leia o inteiro teor e resuma como o relator tratou a gravidade."
- "Quais relatores mais julgaram propaganda antecipada desde 2022?" (use a distribuição dos resultados)
- "Busque no TRE-PE acórdãos sobre captação ilícita de sufrágio em AIJE nas eleições de 2024."
- "Compare como o TRE-PE e o TSE trataram a gravidade no abuso de poder econômico em 2024."
- "Quais TREs mais julgaram fraude à cota de gênero desde 2022?" (distribuição por tribunal)
- "Liste os acórdãos do TRE-PE sobre propaganda irregular em Caruaru."

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

### Publicar uma versão nova

Publicar uma *release* é o que atualiza todos os usuários, na próxima vez que abrirem o Claude.
Um `git push` sem release não chega a ninguém.

1. Troque o número da versão (ex.: `0.3.1`) em `pyproject.toml`, `src\jurisprudencia_tse\__init__.py`
   e `mcpb\manifest.json`.
2. Rode os testes: `.venv\Scripts\python -m pytest` (e, se mexeu na pesquisa, `scripts\testar_mcp.py`).
3. Faça o commit, crie a tag e envie: `git tag v0.3.1` e `git push origin main v0.3.1`.
4. Gere a extensão (precisa do Node.js): `.venv\Scripts\python scripts\empacotar_mcpb.py`.
5. Publique a release com a extensão anexada, com esse mesmo nome de arquivo, para o link de
   download continuar valendo:
   `gh release create v0.3.1 dist\jurisprudencia-tse.mcpb --title "v0.3.1" --notes "O que mudou"`.

A extensão (`mcpb\lancador.py`) só baixa e roda a release mais recente; ela não precisa mudar a
cada versão. Se uma versão sair com defeito, publique logo uma correção ou apague a release com
defeito: o lançador passa a usar a anterior.

O lançador do Claude Code é lido da branch `main` (`mcpb/lancador.py`); mudanças nesse arquivo
chegam a quem usa o Claude Code assim que são enviadas.

Para o Claude usar a cópia em desenvolvimento, aponte o MCP para o Python do `.venv`:
`claude mcp add --scope user jurisprudencia-tse -- C:\caminho\para\jurisprudencia-tse\.venv\Scripts\python.exe -m jurisprudencia_tse`.

## Licença

[MIT](LICENSE).
