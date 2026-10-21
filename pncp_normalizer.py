#!/usr/bin/env python3
"""
📐 PNCP DATA NORMALIZER
========================
Transforma os objetos JSON aninhados da API PNCP em dicionários
"planos" (flat) prontos para escrever em CSV / inserir em banco.

Os nomes dos campos da API foram conferidos em respostas reais (tests/fixtures/).
Cada linha do CSV final representa:
  → 1 resultado registrado para 1 item de 1 contratação
  → com todos os campos da contratação pai, do item e do resultado
"""

from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de extração segura
# ─────────────────────────────────────────────────────────────────────────────

def _s(obj: dict, *keys, default=""):
    """Navega chaves aninhadas com fallback seguro."""
    for k in keys:
        if not isinstance(obj, dict):
            return default
        obj = obj.get(k, default)
    return obj if obj is not None else default


def _f(obj: dict, *keys) -> Optional[float]:
    """Extrai float ou None."""
    v = _s(obj, *keys, default=None)
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _i(obj: dict, *keys) -> Optional[int]:
    v = _s(obj, *keys, default=None)
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Normalização principal
# ─────────────────────────────────────────────────────────────────────────────

def normalizar_contratacao(contratacao: dict) -> dict:
    """Campos da contratação (GET /v1/contratacoes/publicacao)."""
    orgao     = contratacao.get("orgaoEntidade") or {}
    unidade   = contratacao.get("unidadeOrgao") or {}
    orgao_sub = contratacao.get("orgaoSubRogado") or {}
    unid_sub  = contratacao.get("unidadeSubRogada") or {}

    return {
        # Identificação da compra
        "numeroControlePNCP":             _s(contratacao, "numeroControlePNCP"),
        "anoCompra":                      _i(contratacao, "anoCompra"),
        "sequencialCompra":               _i(contratacao, "sequencialCompra"),
        "numeroCompra":                   _s(contratacao, "numeroCompra"),
        "processo":                       _s(contratacao, "processo"),

        # Órgão comprador
        "orgao_cnpj":                     _s(orgao, "cnpj"),
        "orgao_razaoSocial":              _s(orgao, "razaoSocial"),
        "orgao_poder":                    _s(orgao, "poderId"),
        "orgao_esfera":                   _s(orgao, "esferaId"),
        "unidade_codigo":                 _s(unidade, "codigoUnidade"),
        "unidade_nome":                   _s(unidade, "nomeUnidade"),
        "unidade_uf":                     _s(unidade, "ufSigla"),
        "unidade_municipio":              _s(unidade, "municipioNome"),
        "unidade_codigoIBGE":             _s(unidade, "codigoIbge"),

        # Órgão sub-rogado (quando houver)
        "orgaoSubRogado_cnpj":            _s(orgao_sub, "cnpj"),
        "orgaoSubRogado_razaoSocial":     _s(orgao_sub, "razaoSocial"),
        "unidadeSubRogada_codigo":        _s(unid_sub, "codigoUnidade"),
        "unidadeSubRogada_nome":          _s(unid_sub, "nomeUnidade"),

        # Classificação da licitação
        "modalidadeId":                   _i(contratacao, "modalidadeId"),
        "modalidadeNome":                 _s(contratacao, "modalidadeNome"),
        "modoDisputaId":                  _i(contratacao, "modoDisputaId"),
        "modoDisputaNome":                _s(contratacao, "modoDisputaNome"),
        "tipoInstrumentoConvocatorioCod": _i(contratacao, "tipoInstrumentoConvocatorioCodigo"),
        "tipoInstrumentoConvocatorioNom": _s(contratacao, "tipoInstrumentoConvocatorioNome"),
        "srp":                            _s(contratacao, "srp"),        # Sistema de Registro de Preços

        # Situação no momento da publicação (não é a situação atual)
        "situacaoCompraId":               _i(contratacao, "situacaoCompraId"),
        "situacaoCompraNome":             _s(contratacao, "situacaoCompraNome"),

        # Objeto e valores globais
        "objetoCompra":                   _s(contratacao, "objetoCompra"),
        "informacaoComplementar":         _s(contratacao, "informacaoComplementar"),
        "valorTotalEstimado":             _f(contratacao, "valorTotalEstimado"),
        "valorTotalHomologado":           _f(contratacao, "valorTotalHomologado"),

        # Datas
        "dataPublicacaoPncp":             _s(contratacao, "dataPublicacaoPncp"),
        "dataAberturaProposta":           _s(contratacao, "dataAberturaProposta"),
        "dataEncerramentoProposta":       _s(contratacao, "dataEncerramentoProposta"),
        "dataInclusao":                   _s(contratacao, "dataInclusao"),
        "dataAtualizacao":                _s(contratacao, "dataAtualizacao"),

        # Link de origem
        "linkSistemaOrigem":              _s(contratacao, "linkSistemaOrigem"),
        "usuarioNome":                    _s(contratacao, "usuarioNome"),
    }


def normalizar_item(item: dict) -> dict:
    """Campos de um item (GET .../compras/{ano}/{seq}/itens)."""
    return {
        "item_numero":                    _i(item, "numeroItem"),
        "item_descricao":                 _s(item, "descricao"),
        "item_materialServico":           _s(item, "materialOuServico"),
        "item_materialServicoNome":       _s(item, "materialOuServicoNome"),
        "item_categoriaNome":             _s(item, "itemCategoriaNome"),
        "item_tipoBeneficio":             _s(item, "tipoBeneficio"),
        "item_tipoBeneficioNome":         _s(item, "tipoBeneficioNome"),
        "item_situacaoCodigo":            _i(item, "situacaoCompraItem"),
        "item_situacaoNome":              _s(item, "situacaoCompraItemNome"),
        "item_criterioJulgamentoCodigo":  _i(item, "criterioJulgamentoId"),
        "item_criterioJulgamentoNome":    _s(item, "criterioJulgamentoNome"),
        "item_quantidade":                _f(item, "quantidade"),
        "item_unidadeMedida":             _s(item, "unidadeMedida"),
        "item_valorUnitarioEstimado":     _f(item, "valorUnitarioEstimado"),
        "item_valorTotalEstimado":        _f(item, "valorTotal"),
        "item_orcamentoSigiloso":         _s(item, "orcamentoSigiloso"),
        "item_ncmNbsCodigo":              _s(item, "ncmNbsCodigo"),
        "item_ncmNbsDescricao":           _s(item, "ncmNbsDescricao"),
        "item_catalogoCodigo":            _s(item, "catalogoCodigoItem"),
        "item_catalogo":                  _s(item, "catalogo"),
    }


def normalizar_resultado(resultado: dict) -> dict:
    """Campos de um resultado (GET .../itens/{numeroItem}/resultados)."""
    return {
        "resultado_sequencial":           _i(resultado, "sequencialResultado"),
        "resultado_situacaoCodigo":       _i(resultado, "situacaoCompraItemResultadoId"),
        "resultado_situacaoNome":         _s(resultado, "situacaoCompraItemResultadoNome"),

        # Fornecedor vencedor
        "fornecedor_cnpjCpf":             _s(resultado, "niFornecedor"),
        "fornecedor_nome":                _s(resultado, "nomeRazaoSocialFornecedor"),
        "fornecedor_tipoPessoa":          _s(resultado, "tipoPessoa"),            # PJ / PF / PE
        "fornecedor_porteCodigo":         _i(resultado, "porteFornecedorId"),
        "fornecedor_porteNome":           _s(resultado, "porteFornecedorNome"),
        "fornecedor_naturezaJuridica":    _s(resultado, "naturezaJuridicaNome"),
        "fornecedor_paisCodigo":          _s(resultado, "codigoPais"),

        # Proposta / homologação
        "resultado_valorUnitarioHomologado": _f(resultado, "valorUnitarioHomologado"),
        "resultado_valorTotalHomologado":    _f(resultado, "valorTotalHomologado"),
        "resultado_quantidadeHomologada":    _f(resultado, "quantidadeHomologada"),
        "resultado_percentualDesconto":      _f(resultado, "percentualDesconto"),
        "resultado_dataResultado":           _s(resultado, "dataResultado"),
        "resultado_dataAtualizacao":         _s(resultado, "dataAtualizacao"),
        "resultado_dataCancelamento":        _s(resultado, "dataCancelamento"),
    }


def montar_linha(contratacao_flat: dict, item_flat: dict, resultado_flat: dict) -> dict:
    """Combina os três dicionários em uma única linha "plana" para o CSV."""
    return {**contratacao_flat, **item_flat, **resultado_flat}


# Colunas saem das próprias funções: um campo novo aparece no CSV sem lista paralela para manter.
COLUNAS_CSV = list(montar_linha(normalizar_contratacao({}), normalizar_item({}), normalizar_resultado({})))

COLUNAS_SEM_RESULTADO = [
    "numeroControlePNCP", "anoCompra", "sequencialCompra", "processo",
    "orgao_cnpj", "orgao_razaoSocial", "unidade_uf", "unidade_municipio",
    "modalidadeNome", "objetoCompra", "valorTotalEstimado", "valorTotalHomologado",
    "dataPublicacaoPncp", "linkSistemaOrigem",
    "motivo_sem_resultado",
]
