import pytest
import requests

import pncp_client
from pncp_client import FalhaAPI, PNCPClient, _segundos_retry_after


class Resp:
    def __init__(self, status, json=None, headers=None):
        self.status_code = status
        self._json = json
        self.headers = headers or {}
        self.text = "erro"

    def json(self):
        return self._json


class Sessao:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.headers = {}
        self.chamadas = []

    def get(self, url, params=None, timeout=None):
        self.chamadas.append((url, params))
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    monkeypatch.setattr(pncp_client.time, "sleep", lambda s: None)


def cliente(*respostas, tentativas=3):
    return PNCPClient(delay_entre_req=0, max_retries=tentativas, session=Sessao(respostas))


def test_tenta_de_novo_em_erro_do_servidor_e_queda_de_rede():
    c = cliente(Resp(503), requests.exceptions.ConnectionError(), Resp(200, [{"numeroItem": 1}]))
    assert c.listar_itens_compra("1", 2026, 1) == [{"numeroItem": 1}]
    assert len(c.session.chamadas) == 3


def test_falha_persistente_vira_excecao_e_nao_lista_vazia():
    c = cliente(Resp(503), Resp(503), Resp(503))
    with pytest.raises(FalhaAPI):
        c.listar_itens_compra("1", 2026, 1)


def test_erro_do_pedido_nao_tenta_de_novo():
    c = cliente(Resp(400))
    with pytest.raises(FalhaAPI):
        c.listar_contratacoes_publicacao("20260101", "20260107", 6)
    assert len(c.session.chamadas) == 1


def test_404_e_204_sao_ausencia_de_dados():
    assert cliente(Resp(404)).listar_resultados_item("1", 2026, 1, 1) == []
    assert cliente(Resp(204)).listar_contratacoes_publicacao("20260101", "20260101", 6)["data"] == []


def test_listagem_manda_a_modalidade_obrigatoria():
    c = cliente(Resp(200, {"data": [], "totalPaginas": 0}))
    c.listar_contratacoes_publicacao("20260101", "20260107", 8, pagina=2)
    _, params = c.session.chamadas[0]
    assert params["codigoModalidadeContratacao"] == 8 and params["pagina"] == 2


def test_resposta_em_dict_com_data():
    assert cliente(Resp(200, {"data": [{"a": 1}]})).listar_itens_compra("1", 2026, 1) == [{"a": 1}]


def test_retry_after_em_segundos_data_ou_lixo():
    assert _segundos_retry_after("7") == 7
    assert _segundos_retry_after(None) == 10
    assert _segundos_retry_after("lixo") == 10
    assert _segundos_retry_after("Wed, 21 Oct 2015 07:28:00 GMT") == 0   # data no passado
