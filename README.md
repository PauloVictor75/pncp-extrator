# PNCP Extrator

![testes](https://github.com/PauloVictor75/pncp-extrator/actions/workflows/testes.yml/badge.svg)

Extrai do **[PNCP](https://pncp.gov.br)** (Portal Nacional de Contratações Públicas) quem venceu cada item das
contratações públicas brasileiras e por quanto: órgão comprador, item, fornecedor vencedor (CNPJ/CPF, nome, porte)
e valores homologados. Saída em CSV pronto para Excel, Power BI ou pandas.

Usa a API pública e oficial do PNCP — sem navegador, sem CAPTCHA, sem login, uma única dependência (`requests`).

## Destaques técnicos

- **Retomada sem duplicar nem perder dados.** O trabalho é dividido em unidades (janela de 7 dias × modalidade).
  Cada unidade é gravada inteira ou não é gravada: as linhas vão para arquivos parciais e só entram no CSV final
  quando a unidade termina. Queda de rede, erro da API ou Ctrl+C no meio → `--retomar` refaz só o que faltou.
- **Falha não vira "sem dados".** O cliente HTTP distingue "a API não tem nada" (204/404) de "a API falhou"
  (erro depois das novas tentativas). Uma falha não é registrada como contratação sem resultado: a unidade fica
  pendente e o programa termina com código 1.
- **Respeito à API.** Intervalo mínimo entre chamadas, novas tentativas com espera crescente, `Retry-After` no 429.
- **Menos chamadas.** Itens que a API marca como sem resultado (`temResultado: false`) não geram consulta.
- **Testado com respostas reais da API** (`tests/fixtures/`), incluindo falha no meio da extração e retomada.

## Como funciona

```
para cada janela de 7 dias × modalidade:
    GET /consulta/v1/contratacoes/publicacao   (paginado; a modalidade é obrigatória)
        para cada contratação:
            GET /pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/itens
                para cada item com resultado:
                    GET .../itens/{n}/resultados   →  1 linha por resultado
```

| Arquivo | O que faz |
|---|---|
| `pncp_client.py` | Cliente da API: intervalo entre chamadas, novas tentativas, tabela de modalidades |
| `pncp_normalizer.py` | Achata o JSON aninhado em linhas de CSV (nomes de campo conferidos em respostas reais) |
| `pncp_extrator.py` | Janelas, modalidades, gravação por unidade, retomada e linha de comando |
| `enriquecimento.py` | Passo opcional: marca e modelo prováveis a partir da descrição do item |

## Uso

```bash
pip install -r requirements.txt

python pncp_extrator.py                                   # últimos 7 dias, todas as modalidades
python pncp_extrator.py --inicio 20260101 --fim 20260131  # um período
python pncp_extrator.py --modalidades 6,8                 # só pregão eletrônico e dispensa
python pncp_extrator.py --retomar                         # continua a extração anterior
python pncp_extrator.py --help                            # lista os códigos de modalidade
```

Modalidades: 1 Leilão eletrônico · 2 Diálogo competitivo · 3 Concurso · 4 Concorrência eletrônica ·
5 Concorrência presencial · 6 Pregão eletrônico · 7 Pregão presencial · 8 Dispensa · 9 Inexigibilidade ·
10 Manifestação de interesse · 11 Pré-qualificação · 12 Credenciamento · 13 Leilão presencial.

**Volume:** o Brasil publica milhares de contratações por dia (só as dispensas passam de 2 mil em dia útil), e
cada uma pede ao menos duas chamadas à API. Para períodos longos, escolha as modalidades que interessam.

### Docker

```bash
docker build -t pncp-extrator .
docker run --rm -v "$(pwd)/saida_pncp:/app/saida_pncp" pncp-extrator
docker run --rm -v "$(pwd)/saida_pncp:/app/saida_pncp" pncp-extrator \
    python pncp_extrator.py --inicio 20260101 --fim 20260131 --modalidades 6
```

### Marca e modelo (opcional)

A API não informa marca nem modelo. `enriquecimento.py` acrescenta ao CSV as colunas `item_marca_provavel` e
`item_modelo_provavel`, deduzidas da descrição — palpite, separado dos dados oficiais:

```bash
python enriquecimento.py saida_pncp/pncp_resultados_X.csv saida_pncp/enriquecido.csv
```

## Saída

```
saida_pncp/
├── pncp_resultados_AAAAMMDD_HHMMSS.csv     1 linha por resultado de item (fornecedor + valores)
├── pncp_sem_resultado_AAAAMMDD_HHMMSS.csv  contratações sem resultado registrado, com o motivo
├── pncp_progresso.json                     ponto de retomada
└── pncp_extrator.log
```

CSV com `;` e UTF-8 com BOM (abre direto no Excel brasileiro). Principais colunas:

| Grupo | Colunas |
|---|---|
| Contratação | `numeroControlePNCP`, `orgao_cnpj`, `orgao_razaoSocial`, `unidade_uf`, `unidade_municipio`, `modalidadeNome`, `objetoCompra`, `valorTotalEstimado`, `valorTotalHomologado`, `dataPublicacaoPncp`, `linkSistemaOrigem` |
| Item | `item_numero`, `item_descricao`, `item_materialServicoNome`, `item_quantidade`, `item_unidadeMedida`, `item_valorUnitarioEstimado`, `item_valorTotalEstimado`, `item_criterioJulgamentoNome` |
| Resultado | `fornecedor_cnpjCpf`, `fornecedor_nome`, `fornecedor_tipoPessoa`, `fornecedor_porteNome`, `resultado_valorUnitarioHomologado`, `resultado_valorTotalHomologado`, `resultado_quantidadeHomologada`, `resultado_percentualDesconto`, `resultado_dataResultado` |

A lista completa sai das funções de `pncp_normalizer.py` (`COLUNAS_CSV`).

**Situação da contratação:** a listagem do PNCP traz a situação do momento da publicação (quase sempre
"Divulgada"), não a atual. Por isso o critério é o item ter resultado registrado — o que só acontece depois do
julgamento.

## Testes

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Tecnologias

Python 3.11 · requests · pytest · Docker · GitHub Actions

---

Dados públicos do [Portal Nacional de Contratações Públicas](https://pncp.gov.br). Projeto pessoal, sem vínculo
com o governo. Licença MIT.
