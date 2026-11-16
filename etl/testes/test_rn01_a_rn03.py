"""Testes das RN-01, RN-02 e RN-03."""

import unittest

from regras import elegibilidade, identificadores, qualificacoes


class TestRN01Identificadores(unittest.TestCase):

    def test_raiz_preserva_zero_a_esquerda(self):
        self.assertEqual(
            identificadores.raiz_cnpj("00394429000102", "PJ"), "00394429")

    def test_conversao_para_numero_destruiria_a_raiz(self):
        raiz = identificadores.raiz_cnpj("00394429000102", "PJ")
        self.assertNotEqual(raiz, str(int(raiz)))
        self.assertEqual(len(raiz), identificadores.TAMANHO_RAIZ)

    def test_raiz_aceita_cnpj_com_pontuacao(self):
        self.assertEqual(
            identificadores.raiz_cnpj("00.394.429/0001-02", "PJ"), "00394429")

    def test_pessoa_fisica_nao_recebe_raiz(self):
        self.assertEqual(identificadores.raiz_cnpj("12345678901", "PF"), "")

    def test_pj_com_onze_digitos_nao_recebe_raiz(self):
        self.assertEqual(identificadores.raiz_cnpj("12345678901", "PJ"), "")

    def test_pf_com_catorze_digitos_nao_recebe_raiz(self):
        self.assertEqual(identificadores.raiz_cnpj("00394429000102", "PF"), "")

    def test_tipo_que_contradiz_o_tamanho(self):
        self.assertTrue(identificadores.tipo_contradiz_tamanho("12345678901", "PJ"))
        self.assertTrue(identificadores.tipo_contradiz_tamanho("00394429000102", "PF"))
        self.assertFalse(identificadores.tipo_contradiz_tamanho("00394429000102", "PJ"))

    def test_classificacao_por_tamanho(self):
        self.assertEqual(
            identificadores.classificar_identificador("12345678901"),
            identificadores.CPF)
        self.assertEqual(
            identificadores.classificar_identificador("00394429000102"),
            identificadores.CNPJ)
        self.assertEqual(
            identificadores.classificar_identificador("ABC123"),
            identificadores.IRREGULAR)
        self.assertEqual(
            identificadores.classificar_identificador(None),
            identificadores.AUSENTE)

    def test_normalizar_nao_inventa_cnpj_de_outro_tamanho(self):
        self.assertEqual(identificadores.normalizar_cnpj("394429000102"), "")


class TestRN02Elegibilidade(unittest.TestCase):

    def test_valor_menor_que_meio_centavo_arredonda_para_zero(self):
        self.assertEqual(elegibilidade.centavos("0.0001"), 0)
        self.assertFalse(elegibilidade.valor_positivo("0.0001"))

    def test_um_centavo_e_positivo(self):
        self.assertEqual(elegibilidade.centavos("0.01"), 1)
        self.assertTrue(elegibilidade.valor_positivo("0.01"))

    def test_meio_centavo_arredonda_para_cima(self):
        self.assertEqual(elegibilidade.centavos("0.005"), 1)

    def test_corte_de_sanidade_e_inclusivo_no_limite(self):
        self.assertTrue(elegibilidade.elegivel("1000000000.00"))
        self.assertFalse(elegibilidade.elegivel("1000000000.01"))

    def test_contrato_de_receita_sai_dos_indicadores(self):
        self.assertFalse(elegibilidade.elegivel("1000.00", receita=True))
        self.assertTrue(elegibilidade.elegivel("1000.00", receita=False))

    def test_marcar_nao_apaga_o_suspeito(self):
        marca = elegibilidade.marcar("2000000000.00")
        self.assertTrue(marca["contrato_suspeito"])
        self.assertFalse(marca["elegivel_valor"])
        self.assertEqual(marca["valor_centavos"], 200000000000)

    def test_marcar_registra_a_sensibilidade_de_cem_milhoes(self):
        marca = elegibilidade.marcar("500000000.00")
        self.assertFalse(marca["contrato_suspeito"])
        self.assertTrue(marca["acima_sensibilidade"])
        self.assertTrue(marca["elegivel_valor"])

    def test_valor_ilegivel_vira_zero_como_no_try_cast(self):
        self.assertEqual(elegibilidade.centavos("nao e numero"), 0)
        self.assertEqual(elegibilidade.centavos(None), 0)

    def test_nao_ha_valor_negativo_elegivel(self):
        self.assertFalse(elegibilidade.elegivel("-10.00"))


class TestRN03Qualificacoes(unittest.TestCase):

    def test_codigo_aceita_zero_a_esquerda(self):
        self.assertEqual(qualificacoes.codigo("05"), 5)
        self.assertEqual(qualificacoes.codigo(5), 5)
        self.assertIsNone(qualificacoes.codigo(""))

    def test_titular_de_eireli_entra(self):
        self.assertTrue(qualificacoes.socio_elegivel(2, 65))

    def test_socio_pessoa_juridica_nao_e_socio_elegivel(self):
        self.assertFalse(qualificacoes.socio_elegivel(1, 22))

    def test_estrangeiro_nao_entra_na_contagem_de_genero(self):
        self.assertFalse(qualificacoes.socio_elegivel(3, 22))

    def test_socio_sem_capital_e_cotas_em_tesouraria_sao_excluidos(self):
        self.assertFalse(qualificacoes.socio_elegivel(2, 53))
        self.assertFalse(qualificacoes.socio_elegivel(2, 63))
        self.assertEqual(qualificacoes.grupo(53), "excluido")
        self.assertEqual(qualificacoes.grupo(63), "excluido")

    def test_administracao_entra_no_controle_e_sai_da_concentracao(self):
        for cod in (8, 10, 16):
            self.assertTrue(qualificacoes.socio_elegivel(2, cod, para="controle"))
            self.assertFalse(
                qualificacoes.socio_elegivel(2, cod, para="concentracao"))

    def test_participacao_entra_nas_duas(self):
        self.assertTrue(qualificacoes.socio_elegivel(2, 22, para="controle"))
        self.assertTrue(qualificacoes.socio_elegivel(2, 22, para="concentracao"))

    def test_grupos_nao_se_sobrepoem(self):
        self.assertFalse(
            qualificacoes.GRUPO_PARTICIPACAO & qualificacoes.GRUPO_TITULARIDADE)
        self.assertFalse(
            qualificacoes.GRUPO_PARTICIPACAO & qualificacoes.GRUPO_ADMINISTRACAO)
        self.assertFalse(
            qualificacoes.GRUPO_TITULARIDADE & qualificacoes.GRUPO_ADMINISTRACAO)
        self.assertFalse(qualificacoes.PARA_CONTROLE & qualificacoes.EXCLUIDOS)

    def test_tamanhos_dos_grupos_como_a_regra_descreve(self):
        self.assertEqual(len(qualificacoes.GRUPO_PARTICIPACAO), 20)
        self.assertEqual(len(qualificacoes.GRUPO_TITULARIDADE), 8)
        self.assertEqual(len(qualificacoes.GRUPO_ADMINISTRACAO), 9)

    def test_criterio_antigo_por_palavra_difere_da_lista(self):
        """O 53 passava pelo filtro de palavra e a lista de codigos barra."""
        self.assertTrue(
            qualificacoes.socio_elegivel_por_palavra(2, "SOCIO SEM CAPITAL"))
        self.assertFalse(qualificacoes.socio_elegivel(2, 53))

    def test_criterio_antigo_exclui_procurador_e_representante(self):
        self.assertFalse(
            qualificacoes.socio_elegivel_por_palavra(2, "PROCURADOR"))
        self.assertFalse(
            qualificacoes.socio_elegivel_por_palavra(2, "REPRESENTANTE LEGAL"))


if __name__ == "__main__":
    unittest.main()
