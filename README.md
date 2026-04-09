# 🏛️ PNCP Extrator — Contratações Homologadas

Extração automática de **todas as contratações homologadas e encerradas** do
[Portal Nacional de Contratações Públicas (PNCP)](https://pncp.gov.br),
com todos os dados de proposta/resultado por item.

---

## 📦 O que este sistema extrai

Para cada contratação **Homologada (situação 5)** ou **Encerrada (situação 7)**:

| Nível | Dados |
|---|---|
| **Contratação** | Número PNCP, CNPJ e nome do órgão, UF, município, modalidade, objeto, valor estimado, valor homologado, datas, link de origem |
| **Item** | Número, descrição, CATMAT/CATSER, critério de julgamento, quantidade, unidade, valor unitário estimado |
| **Resultado** | Fornecedor vencedor (CNPJ/CPF, nome, porte), valor unitário homologado, valor total homologado, data do resultado |

Cada **linha do CSV** = 1 resultado de proposta de 1 item de 1 contratação.

---

## ⚡ Início rápido

```bash
# 1. Instalar dependências (só 2 pacotes!)
pip install -r requirements.txt

# 2. Executar com padrão (01/07/2025 até hoje, todos os órgãos)
python pncp_extrator.py

# 3. Período personalizado
python pncp_extrator.py --inicio 20250701 --fim 20251231

# 4. Retomar extração interrompida
python pncp_extrator.py --retomar
```

---

## 🐳 Docker

```bash
# Build
docker build -t pncp-extrator .

# Executar (saída montada no host)
docker run -v $(pwd)/saida_pncp:/app/saida_pncp pncp-extrator

# Com período personalizado
docker run -v $(pwd)/saida_pncp:/app/saida_pncp pncp-extrator \
    python pncp_extrator.py --inicio 20250701 --fim 20251231

# Retomar
docker run -v $(pwd)/saida_pncp:/app/saida_pncp pncp-extrator \
    python pncp_extrator.py --retomar
```

---

## 📁 Arquivos gerados

```
saida_pncp/
├── pncp_resultados_YYYYMMDD_HHmmss.csv      ← Dados principais (linha por resultado)
└── pncp_sem_resultado_YYYYMMDD_HHmmss.csv   ← Contratações sem resultado registrado

pncp_progresso.json   ← Estado de retomada (apagar para recomeçar do zero)
pncp_extrator.log     ← Log completo da execução
```

### Separador CSV
O CSV usa **ponto e vírgula (`;`)** como separador e codificação **UTF-8 com BOM**,
compatível diretamente com Excel no Brasil.

---

## 🗂️ Colunas do CSV principal

### Dados da Contratação
| Coluna | Descrição |
|---|---|
| `numeroControlePNCP` | Chave única PNCP (ex: `00394494000136-1-000042/2025`) |
| `anoCompra` / `sequencialCompra` | Ano e sequencial da compra no PNCP |
| `processo` | Número do processo administrativo |
| `orgao_cnpj` | CNPJ do órgão comprador |
| `orgao_razaoSocial` | Nome do órgão |
| `orgao_poder` | E = Executivo, L = Legislativo, J = Judiciário, M = Ministério Público, D = Defensoria |
| `orgao_esfera` | F = Federal, E = Estadual, M = Municipal, D = Distrital |
| `unidade_codigo` | Código da unidade (equivalente ao UASG) |
| `unidade_nome` | Nome da unidade compradora |
| `unidade_uf` | Sigla do estado |
| `unidade_municipio` | Nome do município |
| `unidade_codigoIBGE` | Código IBGE do município |
| `modalidadeNome` | Ex: Pregão - Eletrônico, Concorrência |
| `modoDisputaNome` | Ex: Aberto, Fechado, Aberto e Fechado |
| `srp` | Sistema de Registro de Preços (true/false) |
| `situacaoCompraId` | 5 = Homologada, 7 = Encerrada |
| `situacaoCompraNome` | Nome da situação |
| `objetoCompra` | Descrição do objeto licitado |
| `valorTotalEstimado` | Valor total estimado da licitação |
| `valorTotalHomologado` | Valor total homologado |
| `dataPublicacaoPncp` | Data de publicação no PNCP |
| `dataAberturaProposta` | Data/hora de abertura das propostas |
| `dataEncerramentoProposta` | Data/hora de encerramento |
| `linkSistemaOrigem` | URL do edital no sistema de origem |

### Dados do Item
| Coluna | Descrição |
|---|---|
| `item_numero` | Número do item na licitação |
| `item_descricao` | Descrição do item |
| `item_materialServico` | M = Material, S = Serviço |
| `item_criterioJulgamentoNome` | Ex: Menor Preço, Maior Desconto |
| `item_quantidade` | Quantidade licitada |
| `item_unidadeMedida` | Unidade (UN, KG, L, etc.) |
| `item_valorUnitarioEstimado` | Valor unitário estimado |
| `item_valorTotalEstimado` | Valor total estimado do item |
| `item_codigoCatalogoCodigo` | Código CATMAT/CATSER |
| `item_codigoCatalogoNome` | Descrição CATMAT/CATSER |

### Dados do Resultado (Proposta Vencedora)
| Coluna | Descrição |
|---|---|
| `fornecedor_cnpjCpf` | CNPJ ou CPF do fornecedor vencedor |
| `fornecedor_nome` / `fornecedor_razaoSocial` | Nome do fornecedor |
| `fornecedor_tipoPessoa` | PJ = Pessoa Jurídica, PF = Pessoa Física |
| `fornecedor_porteCodigo` / `fornecedor_porteNome` | Porte (ME, EPP, Grande, etc.) |
| `resultado_valorUnitarioHomologado` | Valor unitário homologado (preço pago) |
| `resultado_valorTotalHomologado` | Valor total homologado do item |
| `resultado_quantidadeHomologada` | Quantidade efetivamente homologada |
| `resultado_dataResultado` | Data do resultado/adjudicação |

---

## 🔄 Lógica de filtro

A API do PNCP não filtra por situação no endpoint de listagem por período.
O sistema busca **todas** as contratações do período e filtra em memória:

```
situacaoCompraId == 5 (Homologada)  ✅ inclui
situacaoCompraId == 7 (Encerrada)   ✅ inclui
demais situações                    ❌ descarta
```

---

## 📊 Estimativa de volume

Para o período 01/07/2025 a hoje (~9 meses), estimativa:
- ~50.000–150.000 contratações homologadas no Brasil inteiro
- ~200.000–500.000 itens
- ~200.000–500.000 linhas no CSV final
- Tempo estimado: 2–6 horas (depende da velocidade da API)

---

## 🆚 Comparação com o sistema anterior (ComprasNet)

| Item | ComprasNet (antigo) | PNCP (novo) |
|---|---|---|
| CAPTCHA | ✅ Obrigatório | ❌ Não existe |
| Browser (Playwright) | ✅ Necessário | ❌ Não necessário |
| OCR (EasyOCR/Tesseract) | ✅ Necessário | ❌ Não necessário |
| Autenticação | N/A | ❌ Não necessária |
| Formato de dados | ZIP com PDF | JSON estruturado |
| Dependências Python | ~15 pacotes pesados | 2 pacotes leves |
| Tamanho da imagem Docker | ~2 GB | ~150 MB |
| Confiabilidade | ~98% (com CAPTCHA solver) | ~99.9% (API oficial) |

---

## ⚙️ Configurações avançadas

Edite as constantes no topo de `pncp_extrator.py`:

```python
DATA_INICIO_PADRAO  = "20250701"   # data padrão se não passar --inicio
TAMANHO_PAGINA      = 50           # registros por página (máx 50)
INTERVALO_DIAS      = 7            # janela de busca em dias
DELAY_ENTRE_REQ     = 0.4          # segundos entre chamadas (respeito à API)
```

---

## 📄 Licença

MIT — uso livre, incluindo uso comercial e governamental.
