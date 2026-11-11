"""Testes das RN-07, RN-08 e RN-09."""

import unittest
from decimal import Decimal

from regras import anonimizacao, concentracao, sancoes


class TestRN07Concentracao(unittest.TestCase):

    def test_socio_de_uma_empresa_nao_e_multiempresa(self):
        multi = concentracao.socios_multiempresa([("ANA|***111111**", "00000001")])
        self.assertEqual(multi, {})

    def test_socio_de_duas_empresas_e_multiempresa(self):
        vinculos = [
            ("ANA|***111111**", "00000001"),
            ("ANA|***111111**", "00000002"),
        ]
        multi = concentracao.socios_multiempresa(vinculos)
        self.assertEqual(len(multi), 1)
        self.assertEqual(multi["ANA|***111111**"], {"00000001", "00000002"})

    def test_mesma_empresa_repetida_nao_conta_duas_vezes(self):
        vinculos = [
            ("ANA|***111111**", "00000001"),
            ("ANA|***111111**", "00000001"),
        ]
        self.assertEqual(concentracao.socios_multiempresa(vinculos), {})

    def test_valor_controlado_soma_as_empresas_do_socio(self):
        vinculos = [
            ("ANA|***111111**", "00000001"),
            ("ANA|***111111**", "00000002"),
        ]
        valores = {"00000001": "1000.00", "00000002": "2500.00"}
        saida = concentracao.valor_controlado(vinculos, valores)
        self.assertEqual(saida["ANA|***111111**"]["valor_controlado"],
                         Decimal("3500.00"))
        self.assertEqual(saida["ANA|***111111**"]["empresas"], 2)

    def test_sobreposicao_quando_a_empresa_tem_dois_socios_multiempresa(self):
        vinculos = [
            ("ANA|***111111**", "00000001"),
            ("ANA|***111111**", "00000002"),
            ("BIA|***222222**", "00000001"),
            ("BIA|***222222**", "00000003"),
        ]
        self.assertEqual(
            concentracao.empresas_sobrepostas(vinculos), {"00000001"})
        saida = concentracao.valor_controlado(
            vinculos, {"00000001": "100", "00000002": "100", "00000003": "100"})
        self.assertTrue(saida["ANA|***111111**"]["sobreposto"])
        self.assertTrue(saida["BIA|***222222**"]["sobreposto"])

    def test_sem_sobreposicao_quando_os_socios_nao_dividem_empresa(self):
        vinculos = [
            ("ANA|***111111**", "00000001"),
            ("ANA|***111111**", "00000002"),
            ("BIA|***222222**", "00000003"),
            ("BIA|***222222**", "00000004"),
        ]
        self.assertEqual(concentracao.empresas_sobrepostas(vinculos), set())

    def test_soma_por_socio_estoura_o_total_e_por_isso_existe_a_marca(self):
        """O ponto da regra: somar valor_controlado conta a empresa duas vezes."""
        vinculos = [
            ("ANA|***111111**", "00000001"),
            ("ANA|***111111**", "00000002"),
            ("BIA|***222222**", "00000001"),
            ("BIA|***222222**", "00000003"),
        ]
        valores = {"00000001": "100", "00000002": "100", "00000003": "100"}
        por_socio = concentracao.valor_controlado(vinculos, valores)
        soma_ingenua = sum(d["valor_controlado"] for d in por_socio.values())
        sem_dupla = concentracao.total_sem_dupla_contagem(vinculos, valores)
        self.assertEqual(soma_ingenua, Decimal("400"))
        self.assertEqual(sem_dupla, Decimal("300"))
        self.assertGreater(soma_ingenua, sem_dupla)

    def test_vinculo_sem_chave_ou_sem_raiz_e_ignorado(self):
        vinculos = [("", "00000001"), ("ANA|***111111**", None)]
        self.assertEqual(concentracao.socios_multiempresa(vinculos), {})


class TestRN08Sancoes(unittest.TestCase):

    def setUp(self):
        self.indice = sancoes.indexar([
            {"cnpj": "00394429000102", "fonte": "CEIS",
             "data_inicio": "2025-06-01", "data_fim": "2025-12-31"},
            {"cnpj": "11222333000144", "fonte": "CNEP",
             "data_inicio": "2025-01-01", "data_fim": None},
        ])

    def test_indice_e_chaveado_pela_raiz(self):
        self.assertIn("00394429", self.indice)
        self.assertIn("11222333", self.indice)

    def test_contrato_assinado_durante_a_sancao_e_marcado(self):
        marca = sancoes.marcar_contrato("00394429", "2025-07-15", self.indice)
        self.assertTrue(marca["fornecedor_sancionado"])
        self.assertEqual(marca["fontes"], ("CEIS",))

    def test_contrato_anterior_a_sancao_nao_e_marcado(self):
        marca = sancoes.marcar_contrato("00394429", "2025-05-31", self.indice)
        self.assertFalse(marca["fornecedor_sancionado"])
        self.assertEqual(marca["motivo"], "sem_sancao_vigente")

    def test_contrato_posterior_ao_fim_da_sancao_nao_e_marcado(self):
        marca = sancoes.marcar_contrato("00394429", "2026-01-01", self.indice)
        self.assertFalse(marca["fornecedor_sancionado"])

    def test_limites_da_vigencia_sao_inclusivos(self):
        for dia in ("2025-06-01", "2025-12-31"):
            self.assertTrue(
                sancoes.marcar_contrato("00394429", dia, self.indice)
                ["fornecedor_sancionado"])

    def test_sancao_sem_fim_continua_vigente(self):
        marca = sancoes.marcar_contrato("11222333", "2030-01-01", self.indice)
        self.assertTrue(marca["fornecedor_sancionado"])

    def test_fornecedor_sem_sancao_nenhuma(self):
        marca = sancoes.marcar_contrato("99999999", "2025-07-15", self.indice)
        self.assertFalse(marca["fornecedor_sancionado"])

    def test_contrato_sem_data_de_assinatura_nao_e_marcado(self):
        marca = sancoes.marcar_contrato("00394429", None, self.indice)
        self.assertFalse(marca["fornecedor_sancionado"])
        self.assertEqual(marca["motivo"], "sem_chave_ou_data")

    def test_formatos_de_data_aceitos(self):
        self.assertEqual(str(sancoes.para_data("15/07/2025")), "2025-07-15")
        self.assertEqual(str(sancoes.para_data("2025-07-15")), "2025-07-15")
        self.assertEqual(str(sancoes.para_data("20250715")), "2025-07-15")
        self.assertIsNone(sancoes.para_data("dia qualquer"))

    def test_competencia_do_quadro_e_declarada(self):
        texto = sancoes.competencia_do_quadro_societario("2026-09-14")
        self.assertIn("2026-09-14", texto)
        self.assertIn("sem data de saida", texto.lower())


class TestRN09Anonimizacao(unittest.TestCase):

    def test_pseudonimo_e_estavel(self):
        a = anonimizacao.pseudonimo("MARIA SILVA", "***123456**")
        b = anonimizacao.pseudonimo("MARIA SILVA", "***123456**")
        self.assertEqual(a, b)

    def test_pseudonimo_nao_contem_o_nome_nem_a_mascara(self):
        p = anonimizacao.pseudonimo("MARIA SILVA", "***123456**")
        self.assertNotIn("MARIA", p.upper())
        self.assertNotIn("123456", p)

    def test_socios_diferentes_tem_pseudonimos_diferentes(self):
        a = anonimizacao.pseudonimo("MARIA SILVA", "***123456**")
        b = anonimizacao.pseudonimo("MARIA SILVA", "***654321**")
        c = anonimizacao.pseudonimo("JOAO SILVA", "***123456**")
        self.assertEqual(len({a, b, c}), 3)

    def test_sal_diferente_muda_o_pseudonimo(self):
        a = anonimizacao.pseudonimo("MARIA SILVA", "***123456**", "sal-a")
        b = anonimizacao.pseudonimo("MARIA SILVA", "***123456**", "sal-b")
        self.assertNotEqual(a, b)

    def test_chave_usa_nome_mais_mascara_porque_a_mascara_colide(self):
        iguais = anonimizacao.chave_socio("ANA", "***111111**")
        diferentes = anonimizacao.chave_socio("BIA", "***111111**")
        self.assertNotEqual(iguais, diferentes)

    def test_mascara_da_receita_e_reconhecida(self):
        self.assertTrue(anonimizacao.cpf_esta_mascarado("***123456**"))
        self.assertFalse(anonimizacao.cpf_esta_mascarado("12345678901"))
        self.assertFalse(anonimizacao.cpf_esta_mascarado(""))

    def test_apresentacao_remove_nome_e_cpf(self):
        saida = anonimizacao.para_apresentacao(
            {"nome": "MARIA SILVA", "cpf_mascarado": "***123456**",
             "cnpj_raiz": "00394429"})
        self.assertNotIn("nome", saida)
        self.assertNotIn("cpf_mascarado", saida)
        self.assertIn("socio_id", saida)
        self.assertEqual(saida["cnpj_raiz"], "00394429")

    def test_cpf_sem_mascara_na_camada_de_dados_levanta_erro(self):
        with self.assertRaises(ValueError):
            anonimizacao.para_apresentacao(
                {"nome": "MARIA SILVA", "cpf": "12345678901"})

    def test_minimo_de_cinco_suprime(self):
        self.assertIsNone(anonimizacao.suprimir(42, n_socios=4))
        self.assertEqual(anonimizacao.suprimir(42, n_socios=5), 42)
        self.assertIsNone(anonimizacao.suprimir(42, n_empresas=1))
        self.assertEqual(anonimizacao.suprimir(42, n_empresas=5), 42)

    def test_suprime_quando_qualquer_um_dos_dois_for_pequeno(self):
        self.assertIsNone(anonimizacao.suprimir(42, n_socios=10, n_empresas=2))
        self.assertEqual(anonimizacao.suprimir(42, n_socios=10, n_empresas=9), 42)

    def test_agregado_publicavel(self):
        self.assertFalse(anonimizacao.agregado_publicavel(n_socios=4))
        self.assertTrue(anonimizacao.agregado_publicavel(n_socios=5))


if __name__ == "__main__":
    unittest.main()
