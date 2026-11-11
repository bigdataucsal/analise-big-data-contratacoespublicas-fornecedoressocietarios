"""Testes das RN-04, RN-05 e RN-06."""

import unittest

from regras import controle, genero, proxy_racial


class TestRN04Genero(unittest.TestCase):

    def test_limiar_de_noventa_por_cento_e_inclusivo(self):
        classe, _, motivo = genero.classificar(90, 10)
        self.assertEqual(classe, genero.FEMININO)
        self.assertEqual(motivo, "classificado")

    def test_abaixo_do_limiar_fica_indeterminado(self):
        classe, _, motivo = genero.classificar(89, 11)
        self.assertEqual(classe, genero.INDETERMINADO)
        self.assertEqual(motivo, "ambiguo")

    def test_nome_ausente_da_base_fica_indeterminado(self):
        classe, prop, motivo = genero.classificar(0, 0)
        self.assertEqual(classe, genero.INDETERMINADO)
        self.assertEqual(motivo, "ausente")
        self.assertEqual(prop, 0.0)

    def test_menos_de_vinte_ocorrencias_fica_indeterminado(self):
        classe, _, motivo = genero.classificar(19, 0)
        self.assertEqual(classe, genero.INDETERMINADO)
        self.assertEqual(motivo, "instavel")

    def test_vinte_ocorrencias_ja_classifica(self):
        classe, _, motivo = genero.classificar(20, 0)
        self.assertEqual(classe, genero.FEMININO)
        self.assertEqual(motivo, "classificado")

    def test_denominador_e_a_soma_dos_sexos(self):
        """Usar um total agregado maior subestimaria a proporcao."""
        classe, prop, _ = genero.classificar(95, 5)
        self.assertEqual(classe, genero.FEMININO)
        self.assertAlmostEqual(prop, 0.95)

    def test_empate_fica_indeterminado(self):
        classe, prop, _ = genero.classificar(50, 50)
        self.assertEqual(classe, genero.INDETERMINADO)
        self.assertAlmostEqual(prop, 0.5)

    def test_sensibilidade_ao_limiar(self):
        """A 80% classifica o que a 95% nao classifica."""
        self.assertEqual(genero.classificar(85, 15, limiar=0.80)[0], genero.FEMININO)
        self.assertEqual(
            genero.classificar(85, 15, limiar=0.95)[0], genero.INDETERMINADO)

    def test_normalizacao_tira_acento_e_sobe_caixa(self):
        self.assertEqual(genero.normalizar("José Antônio"), "JOSE ANTONIO")

    def test_particula_nao_e_primeiro_nome(self):
        self.assertEqual(genero.primeiro_nome("DA SILVA MARIA"), "SILVA")
        self.assertEqual(genero.primeiro_nome("DE OLIVEIRA"), "OLIVEIRA")

    def test_primeiro_nome_curto_e_descartado(self):
        self.assertEqual(genero.primeiro_nome("JO SILVA"), "")

    def test_nome_vazio(self):
        self.assertEqual(genero.primeiro_nome(""), "")
        self.assertEqual(genero.primeiro_nome(None), "")


class TestRN05Controle(unittest.TestCase):

    def test_maioria_feminina_e_mais_de_cinquenta_por_cento(self):
        self.assertEqual(
            controle.classificar_empresa(2, 1, 0, False),
            (controle.FEMININO, "maioria"))

    def test_empate_nao_e_maioria(self):
        self.assertEqual(
            controle.classificar_empresa(1, 1, 0, False),
            (controle.MISTO, "sem_maioria"))

    def test_socio_pj_decide_antes_de_qualquer_contagem(self):
        self.assertEqual(
            controle.classificar_empresa(10, 0, 0, True),
            (controle.MISTO, "socio_pj"))

    def test_mais_de_um_terco_de_indeterminados(self):
        self.assertEqual(
            controle.classificar_empresa(2, 0, 2, False),
            (controle.MISTO, "muitos_indeterminados"))

    def test_exatamente_um_terco_ainda_classifica(self):
        self.assertEqual(
            controle.classificar_empresa(2, 0, 1, False),
            (controle.FEMININO, "maioria"))

    def test_sem_socio_elegivel(self):
        self.assertEqual(
            controle.classificar_empresa(0, 0, 0, False),
            (controle.INDETERMINADO, "sem_socio_elegivel"))

    def test_empresa_sem_linha_na_base_e_universo_a_parte(self):
        classe, motivo = controle.classificar_com_base(0, 0, 0, False, 0)
        self.assertEqual(classe, controle.SEM_SOCIO)
        self.assertEqual(motivo, "sem_linha_na_base")

    def test_so_feminino_e_masculino_contam_como_controle_definido(self):
        self.assertTrue(controle.controle_definido(controle.FEMININO))
        self.assertTrue(controle.controle_definido(controle.MASCULINO))
        self.assertFalse(controle.controle_definido(controle.MISTO))
        self.assertFalse(controle.controle_definido(controle.SEM_SOCIO))

    def test_denominador_do_kpi_exclui_sem_socio(self):
        """Os 30,4% saem de 39.904 sobre 131.423, nao sobre as 239.600."""
        empresas = (
            [(controle.FEMININO,)] * 39904
            + [(controle.MASCULINO,)] * 91519
            + [(controle.SEM_SOCIO,)] * 65001
        )
        definidas = [e for e in empresas if controle.controle_definido(e[0])]
        self.assertEqual(len(definidas), 131423)
        femininas = sum(1 for e in definidas if e[0] == controle.FEMININO)
        self.assertAlmostEqual(100 * femininas / len(definidas), 30.4, places=1)


class TestRN06ProxyRacial(unittest.TestCase):

    def test_percentual_negra_soma_preta_e_parda(self):
        self.assertAlmostEqual(
            proxy_racial.percentual_negra(20, 40, 100), 0.60)

    def test_municipio_sem_total_nao_tem_percentual(self):
        self.assertIsNone(proxy_racial.percentual_negra(0, 0, 0))

    def test_faixas_cobrem_os_extremos_medidos(self):
        self.assertEqual(proxy_racial.faixa_composicao(0.025), "ate_25")
        self.assertEqual(proxy_racial.faixa_composicao(0.608), "de_50_a_75")
        self.assertEqual(proxy_racial.faixa_composicao(0.972), "acima_de_75")
        self.assertEqual(proxy_racial.faixa_composicao(None), "sem_dado")

    def test_atribuir_a_empresa_e_permitido(self):
        saida = proxy_racial.atribuir({"pct_negra": 0.6}, nivel="empresa")
        self.assertEqual(saida["metodo"], "inferencia_ecologica")

    def test_atribuir_a_pessoa_e_proibido(self):
        for nivel in ("socio", "pessoa", "individuo"):
            with self.assertRaises(ValueError):
                proxy_racial.atribuir({"pct_negra": 0.6}, nivel=nivel)


if __name__ == "__main__":
    unittest.main()
