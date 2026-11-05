# Mapeamento da API do portal de jurisprudência do TSE

Levantamento feito em 26/10/2026 sobre o front-end `sjur-pesquisa` versão 2.0.3-7
(`https://jurisprudencia.tse.jus.br/#/jurisprudencia/pesquisa`), a partir do código
JavaScript do portal e de requisições reais observadas no navegador. Serve de base para
o servidor MCP de pesquisa jurisprudencial.

Legenda de confiabilidade: **[verificado]** = testado com requisição real;
**[código]** = extraído do código-fonte do portal, não testado isoladamente.

---

## 1. Arquitetura

| Componente | Endereço | Observação |
|---|---|---|
| Front-end (Angular 7) | `https://jurisprudencia.tse.jus.br/` | Protegido por Akamai: `curl` comum recebe 403. Não é usado pelo MCP. |
| API de pesquisa | `https://sjur-pesquisa-api.tse.jus.br/{tribunal}/sjur-pesquisa-backend/rest/` | Aceita cliente HTTP comum **[verificado]**. |
| Serviços (inteiro teor) | `https://sjur-servicos.tse.jus.br/sjur-servicos/rest/` | Aceita cliente HTTP comum **[verificado]**. |
| Login (opcional) | `https://autenticaje.tse.jus.br/auth/` (Keycloak, realm `eleitor-web`) | Só para favoritos e histórico. A pesquisa é pública. |
| hCaptcha | site key `755c2e18-4bf4-4f28-b992-8c64b77c46b8`, modo invisível | Exigido pelo front-end em toda pesquisa. Ver seção 9. |

`{tribunal}` vem do hostname do front-end:

- `jurisprudencia.tse.jus.br` → `tse`
- `jurisprudencia-tres.tse.jus.br` (portal unificado dos TREs) → `tres` **[código]**

---

## 2. Endpoints

Base da pesquisa: `https://sjur-pesquisa-api.tse.jus.br/tse/sjur-pesquisa-backend/rest/public/pesquisa`

| Método | Caminho | Corpo | Uso | Captcha |
|---|---|---|---|---|
| POST | `/public/pesquisa` | objeto de pesquisa (seção 3) | Pesquisa principal: resultados + agregações | **sim** (`captchaToken`) |
| POST | `/public/pesquisa/pesquisaTokenValidado` | objeto de pesquisa | Recalcula agregações quando há refinamento por facetas | sim |
| POST | `/public/pesquisa/simples` | `{ "termoPesquisa": "<query ES>" }` | Busca direta por query (o portal usa para favoritos) | não enviado pelo front |
| POST | `/public/pesquisa/livre` | objeto de pesquisa | Sem uso visível no front atual | — |
| POST | `/public/pesquisa/classes` | `[]` ou `["TSE"]` | Lista de classes processuais | não **[verificado]** |
| POST | `/public/pesquisa/relatorias` | `[]` | Lista de relatores | não **[verificado]** |
| POST | `/public/pesquisa/eleicoes` | `[]` | Anos de eleição | não **[verificado]** |
| POST | `/public/pesquisa/normas` | `["TSE"]` | Normas para o campo de legislação | não **[verificado]** |
| GET | `/public/pesquisa/rede` | — | Origem de rede (interno) | — |
| GET | `sjur-servicos/rest/download/pdf/{codigoDecisao}` | — | **Inteiro teor em PDF** | não **[verificado]** |
| GET | `sjur-servicos/rest/download/audios/{codigoDecisao}` | — | Áudio da sessão, quando `temInteiroTeorAudio` | não **[código]** |
| POST | `/resultado/download/` | `{"id": ...}` | Exportação legada (blob) | — |

Respostas das listas auxiliares **[verificado]**:

```json
// /classes
[{"siglaClasse":"RESPE","descricaoClasse":"Recurso Especial Eleitoral"}, ...]
// /relatorias
["Admar Gonzaga","Alexandre de Moraes", ...]
// /eleicoes
["2026","2024","2022", ...]
// /normas
[{"norma":"Ato das Disposições Constitucionais Transitórias","sigla":"ADCT","numero":"1988","ano":"1988","tipo":"ATO DAS DISPOSIÇÕES CONSTITUCIONAIS TRANSITÓRIAS"}, ...]
```

---

## 3. `POST /public/pesquisa` — corpo da requisição

Capturado de uma pesquisa real **[verificado]**:

```json
{
  "termoPesquisa": "<string com JSON de query Elasticsearch; ver seção 4>",
  "pagina": 1,
  "tamanho": 25,
  "tribunais": ["tse"],
  "ordenacao": "dj_desc",
  "refinaTermos": [],
  "refinaData": [],
  "refinamento": [],
  "captchaToken": "P1_eyJhbGciOi..."
}
```

| Campo | Valores |
|---|---|
| `pagina` | começa em 0 na primeira página, 1 na segunda etc. (o portal mostrou "Página 2" com `pagina: 1`) |
| `tamanho` | 25 por padrão; o portal oferece outros tamanhos no seletor |
| `tribunais` | `["tse"]` no portal do TSE; `["tre-*"]` por padrão no portal dos TREs **[código]** |
| `ordenacao` | `re` (relevância), `dj_desc`, `dj_asc` (data de julgamento), `dp_desc`, `dp_asc` (data de publicação) |
| `refinamento` | facetas marcadas: lista de `{ "aggregation": "<nome da agregação>", "key": "<valor>" }` **[código]** |
| `refinaData` | `[{ "tipo": "...", "dataInicial": Date, "dataFinal": Date }]` **[código]** |
| `refinaTermos` | termos de "Refinar resultado da pesquisa" **[código]** |

Limite do Elasticsearch: o portal fixa `maximoRegistros = 10000`. Além disso a paginação não avança.

---

## 4. Pesquisa avançada — campos e query gerada

O front-end monta a query Elasticsearch no navegador (módulo `LZov`, classe "motor").
Estrutura base:

```json
{ "bool": { "must": [ LISTA_MUST ], "filter": [ LISTA_FILTER ], "must_not": [], "should": [] } }
```

### 4.1 Campos do formulário "Pesquisa Avançada"

| Rótulo no portal | `formControlName` | Fragmento ES gerado |
|---|---|---|
| Pesquisar em todos os campos | `expressaoLivre` | `{"query_string":{"query":"<texto>","default_operator":"AND","fields":[<FIELDS_TEXT>]}}` |
| Incluir inteiro teor | `inteiroTeor` | acrescenta o campo `"inteiroTeor"` à lista `fields` acima |
| Incluir sinônimos | `sinonimos` | acrescenta `"analyzer":"meu_sinonimos"` ao `query_string` |
| Nº Processo / Nº Decisão / Nº Único / Nº Protocolo | `numero` | `{"query_string":{"query":"*<n>*","fields":["numeroProcesso","numeroDecisao","numeroUnico","numeroUnicoFormatado"],"analyze_wildcard":true}}` |
| Relatorias / Juízes(as) eleitorais | `relatores` | `{"query_string":{"fields":["relatores.nome"],"query":"\"A\" OR \"B\""}}` |
| Classes | `classes` | `{"terms":{"siglaClasse.keyword":["REspEl","AREspEl"]}}` |
| Eleições | `eleicoes` | `{"terms":{"anoEleicao":[2024,2020]}}` |
| Ementa / Decisão / Indexação | `ementaDec` | `{"query_string":{"fields":["indexacoes","textoEmenta","textoDecisao"],"query":"<texto>"}}` |
| Observações | `observacoes` | `{"query_string":{"fields":["anoEleicao","casos","anexos","decisoesOutrosTribunais","textoObservacaoGeral","textoObservacaoLegado"],"query":"<texto>"}}` |
| Partes | `partes` | `{"query_string":{"fields":["partes.nomeParte"],"query":"<texto>"}}` |
| Data inicial / Data final + Julgamento | `datas[].dataInicio`, `datas[].dataFim`, `datas[].tipo = "Julgamento"` | `{"range":{"dataDecisao":{"gte":"dd/MM/yyyy","lte":"dd/MM/yyyy"}}}` |
| idem + Publicação | `datas[].tipo = "Publicação"` | `{"range":{"publicacoes.dataPublicacao":{...}}}` |
| (vários blocos de data) | `datas[]` | combinados em `{"bool":{"should":[...]}}` |
| Pesquisa por legislação: Normas, Nº, Ano | `leis[].norma`, `leis[].numero`, `leis[].ano` | `{"match_phrase":{"referenciasLegislativas.legislacao":{"query":"\"norma\"\"numero\"\"ano\"","slop":2}}}` |
| Art. / Par. / Inc. / Let. / Item | `leis[].tipoLei1..4` + `textoLei1..4` | `{"match_phrase":{"referenciasLegislativas.dispositivos.dispositivo":{"query":"\"Art.: 73\"\"Par.: 10\""}}}` |
| Operador E / OU da legislação | `operadorLei` | `must` (E, padrão) ou `should` (OU) dentro de `{"nested":{"path":"referenciasLegislativas","query":{"bool":{...}}}}` |
| Tipo de decisão | `tipoDecisao` | `{"terms":{"descricaoTipoDecisao.keyword":["Acórdão","Resolução","Decisão sem resolução"]}}` |
| Tribunal (portal dos TREs) | `tribunais` | vai em `filter`: `{"terms":{"siglaTribunalJE.keyword":["TRE-SP"]}}` |

Valores de **Tipo de decisão**: `Acórdão`, `Decisão monocrática`, `Sentença`, `Resolução`,
`Decisão sem resolução`. O padrão do portal marca Acórdão, Resolução e Decisão sem resolução.

Formato do dispositivo legal no índice: `"Art.: 73 Par.: 10"` (rótulos `Art.`, `Par.`, `Inc.`, `Let.`, `Item`).

### 4.2 Campos aceitos pelo motor fora do formulário

Usados por links persistentes e refinamentos (`LISTA_CAMPOS`):

| Campo | Fragmento ES |
|---|---|
| `codigoDecisao` | `{"terms":{"codigoDecisao":[<id>]}}` — busca uma decisão pelo identificador |
| `uf` | `{"terms":{"siglaUF.keyword":["RN"]}}` |
| `municipio` | `{"term":{"nomeMunicipio.keyword":"OURO BRANCO"}}` |
| `etiquetas` | `{"term":{"etiquetas.etiqueta.keyword":"Eleição 2024"}}` |
| `siglaFontePublicacao` | `{"term":{"publicacoes.siglaFontePublicacao.keyword":"DJE"}}` |
| `numeroPublicacao`, `numeroVolume`, `dataPublicacao`, `dataDecisao` | `term` no campo correspondente |

### 4.3 Operadores da pesquisa livre

O texto vai para `query_string` do Elasticsearch, com `default_operator: AND`. O front-end
converte `E`→`AND`, `OU`→`OR`, `NÃO`/`NAO`→`NOT` (também em minúsculas inglesas) e escapa aspas.
Os botões do portal expõem a sintaxe Lucene: `*`, `?`, `""` (frase), `""~` (proximidade),
`~` (fuzzy), `:` (campo), `^` (peso), `+`, `-`, `( )`, `[ ]`, `{ }` (intervalos).

Se o texto for só dígitos, a busca inclui também os campos numéricos (`FIELDS_LONG`); se for
data `dd/mm/aaaa`, usa os campos de data (`FIELDS_DATA`).

### 4.4 Facetas (agregações devolvidas)

`selecionada.keyword` (S/N), `siglaTribunalJE.keyword`, `siglaClasse.keyword`,
`descricaoTipoDecisao.keyword`, `relatores.nome.keyword`, `anoEleicao`,
`assuntos.nomeAssunto.keyword`, `etiquetas.etiqueta.keyword`,
`referenciasLegislativas.legislacao.keyword`, `siglaUF.keyword`,
`naturezaDocumento.keyword`, `tipoDecisaoColegiado.keyword`,
`publicacoes.siglaFontePublicacao.keyword`.

No portal correspondem a: Decisões em destaque, Tribunal, Classe processual, Tipo de decisão,
Relatoria, Eleição, Assuntos, Marcadores temáticos, Referência legislativa, UF de origem,
Natureza do documento, Resultado da votação, Fonte de publicação.

---

## 5. Resposta da pesquisa **[verificado]**

```json
{
  "mensagem": null,
  "totalRegistros": 2782,
  "aggs": [ { "nome": "siglaClasse.keyword", "buckets": [ { "key": "RESPE", "docCount": 925, "checked": false } ] } ],
  "content": [ { ...decisão... } ]
}
```

Campos de cada decisão (`content[]`):

| Grupo | Campos |
|---|---|
| Identificação | `codigoDecisao` (chave para PDF, citação e link), `siglaTribunalJE`, `numeroProcesso`, `numeroDecisao`, `numeroUnico`, `numeroUnicoFormatado` (NPU), `numeroProtocolo`, `origemDecisao` (`PJE` / `SADP`) |
| Classe | `siglaClasse`, `descricaoClasse`, `siglaTipoProcesso`, `nomeTipoProcesso`, `descricaoTipoDecisao` |
| Local e eleição | `siglaUF`, `nomeMunicipio`, `anoEleicao`, `anoEleicaoSuplementar` |
| Datas | `dataDecisao` (`dd/MM/yyyy`), `publicacoes[].dataPublicacao` |
| Textos (HTML) | `textoEmenta`, `textoDecisao`, `textoObservacaoGeral`, `textoIndexacaoLegado`, `textoVotoVencidoLegado`, `textoVotoVistaLegado`, `textoDoutrinaLegado`, `textoObservacaoLegado` |
| Inteiro teor | `temInteiroTeorPDF` (`"true"` como string), `temInteiroTeorAudio`, `quantidadePaginasPDF` |
| Classificação | `selecionada` (S = decisão em destaque), `tipoImportanciaJurisprudencial`, `naturezaDocumento` |
| `relatores[]` | `autoridade`, `nome`, `competencia`, `descricaoCompleta` |
| `publicacoes[]` | `siglaFontePublicacao`, `nomeFontePublicacao`, `numeroPublicacao`, `numeroVolume`, `numeroPagina`, `dataPublicacao` |
| `partes[]` | `nomeParte`, `tipoParte`, `advogados[]` (`nomeAdvogado`, `siglaUF`, `numeroOAB`) |
| `referenciasLegislativas[]` | `legislacao`, `textoNota`, `dispositivos[].dispositivo` |
| `sumulas[]` | `numeroSumula`, `anoSumula`, `descricaoEnunciado`, `siglaOrgaoProlator` |
| `precedentes[]`, `vides[]` | decisões citadas / relacionadas, com `codigoDecisaoPrecedente` / `codigoDecisaoVide` |
| Outros | `assuntos[]`, `etiquetas[]`, `catalogos[]`, `indexacoes[]`, `doutrinas[]`, `casos[]`, `anexos[]`, `argumentosSelecao[]`, `decisoesOutrosTribunais[]`, `decisoesRelacionadasOutrosTribunais[]` |

Cuidados de tratamento:

1. Os termos pesquisados vêm marcados com `<span class='highlighted'>…</span>` em **todos** os
   campos de texto, inclusive nome de relator, partes e fonte de publicação. Remover antes de usar.
2. Ementa e decisão vêm em HTML, com entidades como `&ndash;`. Converter para texto.
3. `partes[]` vem com entradas duplicadas. Deduplicar.
4. Booleanos vêm como string (`"true"`) ou `null`.
5. `textoEmenta` já vem completo. O botão "Mostrar mais" do portal só expande o texto na tela,
   sem requisição de rede **[verificado]**. O MCP não precisa de chamada extra para a ementa
   integral.

---

## 6. Inteiro teor (PDF) **[verificado]**

```
GET https://sjur-servicos.tse.jus.br/sjur-servicos/rest/download/pdf/{codigoDecisao}
```

- É o mesmo link do ícone de PDF em cada ementa (`util.getLinkInteiroTeor`).
- Só existe quando `temInteiroTeorPDF == "true"`.
- Resposta: `Content-Type: application/pdf` e
  `Content-Disposition: attachment; filename=<NPU>_inteiroTeor.pdf`.
- **O corpo não é um PDF puro.** Vem dentro de um envelope `multipart/form-data`:

  ```
  --<boundary>\r\n
  Content-Disposition: form-data; name="file"; filename="inteiroTeor.pdf"\r\n
  Content-Type: application/octet-stream\r\n
  \r\n
  %PDF-1.7 ... %%EOF\r\n
  --<boundary>--\r\n
  ```

  Extrair do primeiro `%PDF` até o último `%%EOF`. O PDF testado (gerado por iText 7) tem
  camada de texto, então dá para extrair o conteúdo sem OCR.
- **Limite de taxa:** duas chamadas seguidas fizeram o servidor responder HTTP 200 com o texto
  `Erro ao tentar recuperar PDF: Excesso de requisições! Favor aguardar alguns instantes e tentar
  novamente.` no lugar do arquivo. O status não sinaliza o erro: checar se o corpo contém `%PDF`.
  Após cerca de 1 minuto a chamada voltou a funcionar. O intervalo exato não foi medido.

Áudio: `GET .../download/audios/{codigoDecisao}` quando `temInteiroTeorAudio` for verdadeiro **[código]**.

---

## 7. Cópia de citação e textos **[verificado]**

O portal não chama a API para copiar: monta o texto no navegador a partir dos campos da
decisão. Botões disponíveis em cada ementa:

| Botão | Função no código | Saída |
|---|---|---|
| Copiar link da decisão | `getLinkDecisao` | `https://jurisprudencia.tse.jus.br/#/jurisprudencia/pesquisa?codigoDecisao={id}&params=s` |
| Copiar ementa sem formatação | `copiarEmentaSemFormatacao` | ementa em texto + cabeçalho |
| Copiar decisão simplificada | `copiarDecisaoSemFormatacao` | decisão em texto + cabeçalho |
| Copiar decisão com ementa | `copiarEmentaDecisaoSemFormatacao` | `Ementa\n\n…\n\nDecisão\n\n…\n\n<cabeçalho>` |
| **Copiar citação** | `copiarCitacaoABNT` | citação ABNT (abaixo) |
| Andamento processual | `consultaProcessual` | PJe: `https://consultaunificadapje.tse.jus.br/#/public/resultado/{NPU}`; SADP: `https://sadppush.tse.jus.br/sadpPush/ExibirDadosProcessoJurisprudencia.do?nprot={numeroProtocolo}&comboTribunal=…` |
| Inteiro teor | link | seção 6 |

### 7.1 Algoritmo da citação ABNT

```
cit = "BRASIL. " + NOME_TRIBUNAL[siglaTribunalJE] + ". "
    + TitleCase(nomeTipoProcesso ?? descricaoClasse)
    + (numeroProcesso ? " " + numeroProcesso + "/" + siglaUF : "")

se relatores tem 1 item:
    cit += ", Relator(a) " + relatores[0].autoridade + " " + relatores[0].nome
se relatores tem 2+ itens:
    para relatores[0] e relatores[1]:
        cit += ", " + descricaoCompleta
               (troca "Relator Designado(a)" por "Relator designado(a)"; "relator" por "Relator(a)")

cit += ", " + descricaoTipoDecisao + " de " + dataDecisao

se houver publicacoes:
    p = publicacoes[0]
    cit += ", Publicado no(a) " + p.nomeFontePublicacao
    se numeroVolume e numeroPublicacao: cit += " " + numeroVolume + "." + numeroPublicacao
    senão se numeroPublicacao:            cit += " " + numeroPublicacao
    se dataPublicacao:                    cit += ", data " + dataPublicacao
    se numeroPagina:                      cit += ", pag. " + numeroPagina
```

`TitleCase` põe a inicial de cada palavra em maiúscula, salvo se o texto contiver "não especificad".

`NOME_TRIBUNAL`: `TSE` → "Tribunal Superior Eleitoral"; `TRE-XX` → "Tribunal Regional Eleitoral
de/do/da <Estado>" (tabela completa das 27 UFs em `getNomeTribunais`, bundle `7.*.js`).

Exemplo real gerado pelo portal:

```
BRASIL. Tribunal Superior Eleitoral. Recurso Especial Eleitoral 060036447/RN, Relator(a) Min.
Floriano <span class='highlighted'>De</span> Azevedo Marques, Acórdão de 03/09/2026, Publicado no(a)
Diário <span class='highlighted'>de</span> Justiça Eletrônico 165, data 21/09/2026
```

O próprio portal deixa o HTML de destaque vazar na citação copiada. O MCP deve aplicar o
algoritmo sobre os campos já limpos.

### 7.2 Cabeçalho usado nas cópias de ementa/decisão

```
<nomeTipoProcesso ?? descricaoClasse> nº<numeroProcesso>, <descricaoTipoDecisao>,
Relator(a) <autoridade> <nome>,
[para cada publicação] Publicação: <sigla> - <nome>[, Tomo <volume>][, <data>].
```

---

## 8. TREs **[verificado em 05/11/2026]**

Mesmo front-end e mesma API do TSE, com estas diferenças:

- Portal: `https://jurisprudencia-tres.tse.jus.br` (também protegido por Akamai) → API em
  `https://sjur-pesquisa-api.tse.jus.br/tres/sjur-pesquisa-backend/rest/public/pesquisa`.
- O link persistente aceita `tribunais=TRE-PE,TRE-PB`. O front-end leva as siglas a dois lugares:
  ao campo `tribunais` do corpo (`["TRE-PE","TRE-PB"]`) e a um `filter`
  `{"terms":{"siglaTribunalJE.keyword":[...]}}`. Sem o parâmetro, `tribunais: ["tre-*"]` e sem filtro
  (todos os 27 TREs).
- `codigoDecisao` funciona igual; o espaço de códigos não colide com o do TSE nos casos testados
  (a busca de um código de TRE no portal do TSE não devolve nada).
- `municipio` (link persistente) gera `{"term":{"nomeMunicipio.keyword":"<valor>"}}`: igualdade exata,
  com o nome como está no índice, em maiúsculas (`RECIFE`, `SÃO BENTO DO UNA`).
- Resposta com o mesmo formato; `siglaTribunalJE` traz a sigla (`TRE-PE`) e `aggs` inclui a faceta
  `siglaTribunalJE.keyword` (distribuição por TRE).
- Listas auxiliares em `/tres/.../public/pesquisa/{classes,relatorias,eleicoes,normas}`, sem captcha:
  `classes` e `relatorias` aceitam `["TRE-PE"]` para restringir a um tribunal (`[]` = todos);
  `normas` só responde com `[]`.
- Inteiro teor: mesmo `sjur-servicos/rest/download/pdf/{codigoDecisao}` do TSE.
- Citação ABNT: mesmo `copiarCitacaoABNT`, com o nome do tribunal pela sigla (seção 7.1).
- Tipos de decisão adicionais nos TREs: `Sentença`, `Decisão monocrática`.
- hCaptcha: mesma site key e mesmo comportamento; nos testes, validou sem desafio mesmo com perfil novo.

---

## 9. hCaptcha — ponto de decisão

O front-end gera um token hCaptcha invisível antes de **cada** chamada a `/public/pesquisa` e
o envia em `captchaToken`. Os demais endpoints mapeados (listas, PDF, áudio) não recebem token
e respondem a um cliente HTTP comum.

Não testei se o servidor rejeita pesquisas sem token: o captcha é a forma que o TSE escolheu
para limitar automação, e contorná-lo não é um caminho aceitável para o projeto. Caminhos
legítimos para a pesquisa:

1. **Pesquisa via navegador real.** O MCP abre o portal num navegador (Playwright, com
   janela visível), preenche a pesquisa e lê a resposta da API. O hCaptcha invisível roda
   normalmente; se aparecer um desafio, o usuário o resolve. Volume baixo, uso pessoal.
2. **Acesso oficial.** Pedir ao TSE (Secretaria de Documentação, ou `8800@tse.jus.br`) uma
   chave de API, liberação de IP ou convênio de dados. É o caminho estável para uso contínuo.
3. **Híbrido.** Pesquisa pelo caminho 1 ou 2; inteiro teor, listas e citação por HTTP direto,
   pois esses endpoints são públicos e sem captcha.

Os endpoints sem captcha também têm limite de taxa (seção 6). O MCP deve espaçar as chamadas
e guardar em cache os PDFs já baixados.

Navegador sem janela (headless) não serve: o Akamai do front-end responde `Access Denied` (HTTP 403)
ao user agent `HeadlessChrome` **[verificado em 26/10/2026]**. O MCP usa janela comum, posicionada fora da área visível da tela (desde a 0.1.2; antes, minimizada).

### 9.1 Comportamento quando o captcha não é resolvido **[verificado por simulação]**

Simulado em 26/10/2026 travando a resposta do hCaptcha no navegador (sem desafio real):

1. O portal espera **15 segundos** pelo token (`executeCaptcha`, timeout fixo no código).
2. Esgotado o prazo, registra no console `Timeout ao validar o hCaptcha.` e **não envia** a pesquisa.
3. A tela fica acinzentada com o indicador de carregamento girando. Nenhuma mensagem aparece.
4. A tela de resultados para de responder: com o captcha já normal, clicar de novo em
   Pesquisar não gera requisição. O erro encerra a assinatura que dispara as pesquisas.
5. Recarregar a página e clicar em Pesquisar recupera. Os parâmetros da URL (termo, página,
   ordenação) são preservados, mas a pesquisa só sai depois do clique.

Consequência: se o desafio levar mais de 15 segundos, a solução do usuário chega tarde e é
descartada (`__captchaResolve` ignora respostas depois do timeout). Ainda não verifiquei se o
hCaptcha passa a liberar sem desafio nas pesquisas seguintes.

Para o MCP pelo caminho do navegador:

- detectar o iframe de desafio visível ou o erro de timeout no console;
- devolver ao Claude o estado `captcha_pendente` em vez de bloquear a ferramenta;
- depois que o usuário avisar que resolveu, recarregar a página e acionar Pesquisar de novo.

---

## 10. Ferramentas propostas para o MCP

| Ferramenta | Entrada | Endpoint | Saída |
|---|---|---|---|
| `tse_pesquisar` | texto livre, inteiro teor, sinônimos, número, relatores, classes, eleições, ementa/decisão, partes, datas (julgamento/publicação), legislação, tipo de decisão, UF, ordenação, página | `/public/pesquisa` (via caminho da seção 9) | lista enxuta: `codigoDecisao`, classe e número, NPU, relator, datas, ementa em texto, flag de PDF; total e facetas |
| `tse_obter_decisao` | `codigoDecisao` | pesquisa com `{"terms":{"codigoDecisao":[id]}}` | decisão completa limpa |
| `tse_inteiro_teor` | `codigoDecisao` | `GET download/pdf/{id}` | texto extraído do PDF e caminho do arquivo salvo |
| `tse_citacao` | `codigoDecisao` ou decisão já obtida | local (seção 7.1) | citação ABNT limpa, cabeçalho e link permanente |
| `tse_listar` | `classes` / `relatores` / `eleicoes` / `normas` | listas auxiliares | valores válidos para os filtros |

---

## 11. Pendências

- Medir o intervalo mínimo entre downloads de PDF.
- Confirmar a semântica de `pagina` (base 0) e o formato exato de `refinamento` e `refinaData`
  capturando uma pesquisa com faceta marcada.
- Decidir o caminho da seção 9.
