#!/usr/bin/env python3
"""
📐 PNCP DATA NORMALIZER
========================
Transforma os objetos JSON aninhados da API PNCP em dicionários
"planos" (flat) prontos para escrever em CSV / inserir em banco.

Cada linha do CSV final representa:
  → 1 resultado de proposta (vencedor de item)
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
    """
    Extrai os campos relevantes do objeto contratação retornado pela API
    /v1/contratacoes/publicacao ou /v1/orgaos/{cnpj}/compras/{ano}/{seq}
    """
    orgao      = contratacao.get("orgaoEntidade") or {}
    unidade    = contratacao.get("unidadeOrgao") or {}
    orgao_sub  = contratacao.get("orgaoSubRogado") or {}
    unid_sub   = contratacao.get("unidadeSubRogada") or {}

    return {
        # Identificação da compra
        "numeroControlePNCP":             _s(contratacao, "numeroControlePNCP"),
        "anoCompra":                      _i(contratacao, "anoCompra"),
        "sequencialCompra":               _i(contratacao, "sequencialCompra"),
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

        # Situação atual
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
    """
    Extrai os campos relevantes de cada item de uma compra.
    Com fallback automático para marca/modelo via descrição.
    """

    descricao = _s(item, "descricao", default="")

    # 🔹 Dados vindos da API
    marca_api = _s(item, "marcaFabricante")
    modelo_api = _s(item, "modeloVersao")

    marca = marca_api or ""
    modelo = modelo_api or ""

    # 🔥 Fallback (se API não trouxe)
    if not marca or not modelo:
        d = descricao.lower()

        # marcas comuns
        if "dell" in d:
            marca = marca or "Dell"
        elif "hp" in d:
            marca = marca or "HP"
        elif "lenovo" in d:
            marca = marca or "Lenovo"
        elif "asus" in d:
            marca = marca or "Asus"
        elif "acer" in d:
            marca = marca or "Acer"

        # modelos comuns
        if "inspiron" in d:
            modelo = modelo or "Inspiron"
        elif "thinkpad" in d:
            modelo = modelo or "ThinkPad"
        elif "elitebook" in d:
            modelo = modelo or "EliteBook"
        elif "aspire" in d:
            modelo = modelo or "Aspire"

    return {
        "item_numero":                    _i(item, "numeroItem"),
        "item_descricao":                 descricao,
        "item_materialServico":           _s(item, "materialOuServico"),
        "item_materialServicoNome":       _s(item, "materialOuServicoNome"),
        "item_tipoBeneficio":             _s(item, "tipoBeneficio"),
        "item_tipoBeneficioNome":         _s(item, "tipoBeneficioNome"),
        "item_situacaoCodigo":            _i(item, "situacaoCompraItemCodigo"),
        "item_situacaoNome":              _s(item, "situacaoCompraItemNome"),
        "item_criterioJulgamentoCodigo":  _i(item, "criterioJulgamentoCodigo"),
        "item_criterioJulgamentoNome":    _s(item, "criterioJulgamentoNome"),
        "item_quantidade":                _f(item, "quantidade"),
        "item_unidadeMedida":             _s(item, "unidadeMedida"),
        "item_valorUnitarioEstimado":     _f(item, "valorUnitarioEstimado"),
        "item_valorTotalEstimado":        _f(item, "valorTotalEstimado"),
        "item_orcamentoSigiloso":         _s(item, "orcamentoSigiloso"),
        "item_ncmNbs":                    _s(item, "ncmNbs"),
        "item_codigoCatalogoCodigo":      _s(item, "codigoCatalogoCodigo"),
        "item_codigoCatalogoNome":        _s(item, "codigoCatalogoNome"),

        # 🔥 RESULTADO FINAL (melhorado)
        "item_marca":                     marca,
        "item_modelo":                    modelo,
    }



def normalizar_resultado(resultado: dict) -> dict:
    """
    Extrai os campos relevantes de cada resultado (proposta vencedora) de um item.
    """
    fornecedor = resultado.get("fornecedor") or {}
    pais       = resultado.get("paisFornecedor") or {}

    return {
        "resultado_sequencial":           _i(resultado, "sequencialResultado"),
        "resultado_situacaoCodigo":       _i(resultado, "situacaoCompraItemResultadoCodigo"),
        "resultado_situacaoNome":         _s(resultado, "situacaoCompraItemResultadoNome"),

        # Fornecedor vencedor
        "fornecedor_cnpjCpf":             _s(fornecedor, "cnpjCpf"),
        "fornecedor_nome":                _s(fornecedor, "nome"),
        "fornecedor_razaoSocial":         _s(fornecedor, "razaoSocial"),
        "fornecedor_niFornecedor":        _s(resultado, "niFornecedor"),
        "fornecedor_tipoPessoa":          _s(resultado, "tipoPessoa"),            # PJ / PF
        "fornecedor_porteCodigo":         _s(resultado, "porteCodigo"),
        "fornecedor_porteNome":           _s(resultado, "porteNome"),
        "fornecedor_paisCodigo":          _s(pais, "codigo"),
        "fornecedor_paisNome":            _s(pais, "nome"),

        # Proposta / homologação
        "resultado_valorUnitarioHomologado":  _f(resultado, "valorUnitarioHomologado"),
        "resultado_valorTotalHomologado":     _f(resultado, "valorTotalHomologado"),
        "resultado_quantidadeHomologada":     _f(resultado, "quantidadeHomologada"),
        "resultado_dataResultado":            _s(resultado, "dataResultado"),
        "resultado_dataHoraAtualizacao":      _s(resultado, "dataHoraAtualizacao"),
        "resultado_numeroItemCompra":         _i(resultado, "numeroItemCompra"),

        # Origem do resultado
        "resultado_orcamentoCodigo":          _s(resultado, "orcamentoCodigo"),
    }


def montar_linha(contratacao_flat: dict, item_flat: dict, resultado_flat: dict) -> dict:
    """
    Combina os três dicionários em uma única linha "plana" para o CSV.
    Chaves duplicadas: o resultado tem prioridade, depois item, depois contratação.
    """
    linha = {}
    linha.update(contratacao_flat)
    linha.update(item_flat)
    linha.update(resultado_flat)
    return linha
