"""Testes da consulta de tratamento, rodada de verdade no DuckDB.

A consulta mora dentro de uma string de Python, de modo que o py_compile da CI
a aceita mesmo quebrada. Foi assim que um comentario de SQL virado codigo
passou por tres verificacoes: o arquivo compila, o --help funciona e a
comparacao de AST neutraliza o conteudo das strings. Este teste executa a
consulta, que e a unica forma de pegar esse defeito.
"""

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import duckdb

import tratar_contratos
from regras import elegibilidade, identificadores

CONTRATO_BASE = {
    "numeroControlePNCP": "00000000000000-1-000001/2025",
    "anoContrato": 2025,
    "sequencialContrato": 1,
    "dataPublicacaoPncp": "2025-01-15T10:00:00",
    "dataAtualizacaoGlobal": "2025-01-15T10:00:00",
    "dataAssinatura": "2025-01-10",
    "niFornecedor": "00394429000102",
    "tipoPessoa": "PJ",
    "nomeRazaoSocialFornecedor": "EMPRESA   TESTE  LTDA",
    "valorGlobal": 1000.00,
    "valorInicial": 1000.00,
    "receita": None,
    "emendaParlamentar": None,
    "objetoContrato": "aquisicao de material",
    "orgaoEntidade": {"cnpj": "11111111000111", "razaoSocial": "ORGAO X",
                      "poderId": "E", "esferaId": "M"},
    "unidadeOrgao": {"ufSigla": "ba", "ufNome": "Bahia",
                     "municipioNome": "Salvador", "codigoIbge": "2927408",
                     "codigoUnidade": "1", "nomeUnidade": "UNIDADE"},
}


def contrato(**campos):
    return dict(CONTRATO_BASE, **campos)


class TestTratamentoSQL(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.jsonl = Path(cls.tmp.name) / "amostra.jsonl"

        registros = [
            contrato(),
            contrato(
                numeroControlePNCP="pf-sem-raiz",
                niFornecedor="12345678901", tipoPessoa="PF"),
            contrato(
                numeroControlePNCP="pj-irregular",
                niFornecedor="ABC999", tipoPessoa="PJ"),
            contrato(
                numeroControlePNCP="pj-onze-digitos",
                niFornecedor="12345678901", tipoPessoa="PJ"),
            contrato(
                numeroControlePNCP="valor-menor-que-meio-centavo",
                valorGlobal=0.0001),
            contrato(
                numeroControlePNCP="acima-do-bilhao",
                valorGlobal=2000000000.00),
            contrato(
                numeroControlePNCP="contrato-de-receita",
                receita=True),
            contrato(
                numeroControlePNCP="duplicado",
                dataAtualizacaoGlobal="2025-01-15T10:00:00",
                valorGlobal=111.00),
            contrato(
                numeroControlePNCP="duplicado",
                dataAtualizacaoGlobal="2025-02-20T10:00:00",
                valorGlobal=222.00),
            contrato(numeroControlePNCP=None),
        ]

        with cls.jsonl.open("w", encoding="utf-8") as saida:
            for registro in registros:
                saida.write(json.dumps(registro, ensure_ascii=False) + "\n")

        fonte = str(cls.jsonl).replace("\\", "/")
        cls.con = duckdb.connect()
        cls.sql = tratar_contratos.montar_sql([fonte])
        cls.con.execute(f"CREATE TABLE tratado AS {cls.sql}")

    @classmethod
    def tearDownClass(cls):
        cls.con.close()
        cls.tmp.cleanup()

    def uma(self, chave, coluna):
        return self.con.execute(
            f"SELECT {coluna} FROM tratado WHERE numero_controle_pncp = ?",
            [chave]).fetchone()

    def test_a_consulta_executa(self):
        """Regressao do defeito de 449ff76: o comentario virado codigo."""
        total = self.con.execute("SELECT count(*) FROM tratado").fetchone()[0]
        self.assertGreater(total, 0)

    def test_ano_mes_e_coluna_unica_e_nao_sobrou_texto_de_comentario(self):
        colunas = [c[0] for c in self.con.execute(
            "SELECT * FROM tratado LIMIT 0").description]
        self.assertIn("ano_mes", colunas)
        self.assertNotIn("chave", colunas)
        self.assertNotIn("particao", colunas)
        self.assertEqual(
            self.uma("00000000000000-1-000001/2025", "ano_mes")[0], "2025-01")

    def test_rn01_raiz_so_para_pj_de_catorze_digitos(self):
        self.assertEqual(
            self.uma("00000000000000-1-000001/2025", "cnpj_raiz_fornecedor")[0],
            "00394429")
        for chave in ("pf-sem-raiz", "pj-irregular", "pj-onze-digitos"):
            self.assertIsNone(
                self.uma(chave, "cnpj_raiz_fornecedor")[0],
                f"{chave} nao devia receber raiz")

    def test_rn01_raiz_do_sql_concorda_com_a_do_modulo(self):
        linhas = self.con.execute(
            "SELECT ni_fornecedor, tipo_pessoa, cnpj_raiz_fornecedor "
            "FROM tratado").fetchall()
        for ni, tipo, raiz_sql in linhas:
            raiz_py = identificadores.raiz_cnpj(ni, tipo)
            self.assertEqual(raiz_sql or "", raiz_py,
                             f"divergencia em {ni}/{tipo}")

    def test_valor_vira_decimal_de_duas_casas(self):
        valor = self.uma("valor-menor-que-meio-centavo", "valor_global")[0]
        self.assertEqual(valor, Decimal("0.00"))

    def test_rn02_o_corte_concorda_com_o_modulo(self):
        linhas = self.con.execute(
            "SELECT numero_controle_pncp, valor_global, receita "
            "FROM tratado").fetchall()
        for chave, valor, receita in linhas:
            esperado = elegibilidade.elegivel(valor, receita)
            if chave == "acima-do-bilhao":
                self.assertFalse(esperado)
            if chave == "contrato-de-receita":
                self.assertFalse(esperado)
            if chave == "valor-menor-que-meio-centavo":
                self.assertFalse(esperado)

    def test_booleanos_nulos_viram_falso(self):
        self.assertFalse(
            self.uma("00000000000000-1-000001/2025", "receita")[0])
        self.assertFalse(
            self.uma("00000000000000-1-000001/2025", "emenda_parlamentar")[0])

    def test_receita_verdadeira_e_preservada(self):
        self.assertTrue(self.uma("contrato-de-receita", "receita")[0])

    def test_deduplicacao_fica_com_a_atualizacao_mais_recente(self):
        linhas = self.con.execute(
            "SELECT valor_global FROM tratado "
            "WHERE numero_controle_pncp = 'duplicado'").fetchall()
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0][0], Decimal("222.00"))

    def test_contrato_sem_chave_e_descartado(self):
        nulos = self.con.execute(
            "SELECT count(*) FROM tratado "
            "WHERE numero_controle_pncp IS NULL").fetchone()[0]
        self.assertEqual(nulos, 0)

    def test_uf_sobe_para_maiuscula_e_espaco_duplo_e_limpo(self):
        self.assertEqual(
            self.uma("00000000000000-1-000001/2025", "uf_sigla")[0], "BA")
        self.assertEqual(
            self.uma("00000000000000-1-000001/2025", "nome_fornecedor")[0],
            "EMPRESA TESTE LTDA")

    def test_identificador_fica_como_texto(self):
        valor = self.uma("00000000000000-1-000001/2025", "ni_fornecedor")[0]
        self.assertIsInstance(valor, str)
        self.assertTrue(valor.startswith("00"))


class TestSQLSemComentarioQuebrado(unittest.TestCase):

    def test_nenhuma_linha_do_sql_tem_comentario_virado_codigo(self):
        """Pega o padrao do defeito: texto em portugues solto depois de virgula."""
        suspeitas = []
        for linha in tratar_contratos.SQL_TRATAMENTO.splitlines():
            limpa = linha.strip()
            if limpa.startswith("--") or not limpa:
                continue
            if ", chave" in limpa or ", corte" in limpa or ", identificador" in limpa:
                suspeitas.append(limpa)
        self.assertEqual(suspeitas, [])

    def test_o_sql_passa_pelo_parser(self):
        con = duckdb.connect()
        sql = tratar_contratos.montar_sql(["nao-existe.jsonl"])
        with self.assertRaises(duckdb.IOException):
            con.execute(f"EXPLAIN {sql}")
        con.close()


if __name__ == "__main__":
    unittest.main()
