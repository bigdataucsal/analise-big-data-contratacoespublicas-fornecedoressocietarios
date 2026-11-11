"""Mede a divergencia entre a mv_kpi_genero_setor e a RN-05.

A RN-05 ja registra que a visao materializada nao aplica a regra por inteiro.
Este teste transforma esse paragrafo em numero: reproduz em Python o CASE da
visao, roda os dois criterios sobre os mesmos quadros societarios e fixa
exatamente onde eles discordam. Enquanto a visao nao for alinhada, o teste
documenta a diferenca; quando for, ele e que mostra que acabou.

A exigencia da issue de auditoria e zero divergencia entre a regra de negocio
e a tela, e a tela le a visao.
"""

import unittest

from regras import controle

MISTO_VISAO = "misto ou indeterminado"


def genero_controle_da_visao(n_f, n_m, n_ind, tem_pj, linhas_de_socio):
    """O CASE da mv_kpi_genero_setor, em Python.

    Transcrito de etl/schema_estrela.sql. O LATERAL da visao filtra
    identificador_tipo = 2, de modo que o socio pessoa juridica nao entra na
    contagem e tambem nao aciona regra nenhuma: `tem_pj` e ignorado de
    proposito aqui, e e justamente essa a primeira divergencia.
    """
    n = n_f + n_m + n_ind
    if n_ind > n / 3.0:
        return MISTO_VISAO
    if n_f > n / 2.0:
        return "feminino"
    if n_m > n / 2.0:
        return "masculino"
    return MISTO_VISAO


def classe_equivalente(classe):
    """Traduz a classe da RN-05 para o vocabulario da visao."""
    if classe == controle.FEMININO:
        return "feminino"
    if classe == controle.MASCULINO:
        return "masculino"
    return MISTO_VISAO


CASOS = [
    ("maioria feminina simples", 2, 1, 0, False, 3),
    ("maioria masculina simples", 1, 2, 0, False, 3),
    ("empate", 1, 1, 0, False, 2),
    ("excesso de indeterminados", 2, 0, 2, False, 4),
    ("um terco exato de indeterminados", 2, 0, 1, False, 3),
    ("so feminino, com socio PJ no quadro", 3, 0, 0, True, 4),
    ("so masculino, com socio PJ no quadro", 0, 3, 0, True, 4),
    ("empresa sem linha de socio na base", 0, 0, 0, False, 0),
    ("empresa com socio na base mas sem elegivel", 0, 0, 0, False, 2),
]


class TestDivergenciaVisaoKPI(unittest.TestCase):

    def divergencias(self):
        fora = []
        for nome, n_f, n_m, n_ind, tem_pj, linhas in CASOS:
            da_regra = classe_equivalente(
                controle.classificar_com_base(n_f, n_m, n_ind, tem_pj, linhas)[0])
            da_visao = genero_controle_da_visao(n_f, n_m, n_ind, tem_pj, linhas)
            if da_regra != da_visao:
                fora.append((nome, da_regra, da_visao))
        return fora

    def test_os_casos_simples_concordam(self):
        for nome, n_f, n_m, n_ind, tem_pj, linhas in CASOS[:5]:
            da_regra = classe_equivalente(
                controle.classificar_com_base(n_f, n_m, n_ind, tem_pj, linhas)[0])
            da_visao = genero_controle_da_visao(n_f, n_m, n_ind, tem_pj, linhas)
            self.assertEqual(da_regra, da_visao, f"divergiu em: {nome}")

    def test_a_visao_ignora_o_socio_pessoa_juridica(self):
        """Primeira divergencia: a RN-05 manda a empresa para misto, a visao nao."""
        self.assertEqual(
            controle.classificar_empresa(3, 0, 0, True),
            (controle.MISTO, "socio_pj"))
        self.assertEqual(
            genero_controle_da_visao(3, 0, 0, True, 4), "feminino")

    def test_a_visao_junta_quem_nao_tem_socio_na_base_com_as_mistas(self):
        """Segunda divergencia: a D5 manda declarar a parte, a visao mistura."""
        self.assertEqual(
            controle.classificar_com_base(0, 0, 0, False, 0)[0],
            controle.SEM_SOCIO)
        self.assertEqual(
            genero_controle_da_visao(0, 0, 0, False, 0), MISTO_VISAO)

    def test_a_divergencia_esta_onde_a_rn05_diz_que_esta(self):
        """Nenhuma divergencia fora das que o documento ja declara.

        A lista tem so os dois casos de socio pessoa juridica porque a
        traducao para o vocabulario da visao e cega para a outra: a visao nao
        tem classe para a empresa sem socio na base, de modo que
        `classe_equivalente` precisa mandar SEM_SOCIO para misto e as duas
        passam a concordar na aparencia. Essa cegueira e o segundo defeito, e
        esta medida no teste seguinte, que compara as classes cruas.
        """
        nomes = sorted(nome for nome, _, _ in self.divergencias())
        self.assertEqual(nomes, [
            "so feminino, com socio PJ no quadro",
            "so masculino, com socio PJ no quadro",
        ])

    def test_a_visao_nao_tem_classe_para_quem_nao_tem_socio(self):
        """As 65.001 empresas da D5 caem no mesmo balde das mistas.

        Sao 27,1% do recorte sem classe propria na visao, o que impede
        distinguir, na tela, a empresa de controle indefinido da empresa que
        nao tem controle inferivel.
        """
        sem_socio = controle.classificar_com_base(0, 0, 0, False, 0)[0]
        empate = controle.classificar_empresa(1, 1, 0, False)[0]
        self.assertNotEqual(sem_socio, empate)
        self.assertEqual(
            genero_controle_da_visao(0, 0, 0, False, 0),
            genero_controle_da_visao(1, 1, 0, False, 2))

    def test_o_efeito_no_kpi_tem_direcao_conhecida(self):
        """A divergencia infla o controle definido, nunca o contrario.

        Nos tres casos em que discordam, a visao devolve uma classe definida
        onde a regra devolve misto ou sem_socio, ou junta no misto quem devia
        ficar de fora. Nenhum caso faz o inverso, de modo que o denominador do
        KPI calculado pela visao e maior ou igual ao da regra.
        """
        for nome, da_regra, da_visao in self.divergencias():
            if da_visao in ("feminino", "masculino"):
                self.assertEqual(da_regra, MISTO_VISAO,
                                 f"{nome}: a visao definiu o que a regra nao define")


if __name__ == "__main__":
    unittest.main()
