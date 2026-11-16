"""Prova que o agregado do banco e a RN-05 classificam igual.

O `agg_kpi_genero_setor` e alimentado pelo SQL_CONTROLE do
construir_agregados.py, e e dele que sai o KPI de controle feminino. Se esse
CASE e o regras/controle.py discordarem, o numero da tela deixa de ser o
numero da regra, que e exatamente o que a auditoria pede para nao acontecer.

O teste le o SQL do modulo e executa o CASE de verdade no DuckDB, em vez de
guardar uma copia dele aqui. A versao anterior deste arquivo guardava a copia,
e envelheceu em silencio: a T2 trocou a visao materializada por tabela de
agregado e corrigiu a regra, e o teste continuou passando afirmando uma
divergencia que ja nao existia. Lendo da fonte, ou ele acompanha a mudanca ou
falha.
"""

import re
import unittest

import duckdb

import construir_agregados
from regras import controle

CASE = re.compile(r"(CASE\s.*?END)\s+AS\s+genero_controle", re.S | re.I)

COLUNAS = ("rotulo", "id_fornecedor", "tem_pj", "n", "n_fem", "n_masc",
           "n_ind", "n_nulo")

# rotulo, id_fornecedor, tem_pj, n, n_fem, n_masc, n_ind, n_nulo
CASOS = [
    ("maioria feminina",              1, False, 3, 2, 1, 0, 0),
    ("maioria masculina",             2, False, 3, 1, 2, 0, 0),
    ("empate",                        3, False, 2, 1, 1, 0, 0),
    ("um terco exato de indeterm",    4, False, 3, 2, 0, 1, 0),
    ("mais de um terco indeterm",     5, False, 4, 2, 0, 2, 0),
    ("socio pj com quadro feminino",  6, True,  3, 3, 0, 0, 0),
    ("socio pj com quadro masculino", 7, True,  3, 0, 3, 0, 0),
    ("sem socio elegivel",            8, False, 0, 0, 0, 0, 0),
    ("socio sem genero",              9, False, 3, 2, 1, 0, 1),
    ("socio sem genero e pj",        10, True,  3, 2, 1, 0, 2),
    ("sem linha de socio na base", None, None, None, None, None, None, None),
]


def nulo_sql(valor):
    if valor is None:
        return "NULL"
    if isinstance(valor, bool):
        return "TRUE" if valor else "FALSE"
    return str(valor)


class TestAgregadoVsRegra(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        achado = CASE.search(construir_agregados.SQL_CONTROLE)
        if not achado:
            raise AssertionError(
                "nao achei o CASE ... AS genero_controle no SQL_CONTROLE do "
                "construir_agregados.py. Se a classificacao mudou de lugar, "
                "este teste precisa ser reapontado em vez de removido"
            )
        cls.case_sql = achado.group(1)

        linhas = ",\n    ".join(
            "(" + ", ".join(
                [f"'{c[0]}'"] + [nulo_sql(v) for v in c[1:]]) + ")"
            for c in CASOS
        )
        consulta = f"""
            SELECT q.rotulo, {cls.case_sql} AS genero_controle
            FROM (VALUES
    {linhas}
            ) AS q({", ".join(COLUNAS)})
        """
        con = duckdb.connect()
        try:
            cls.do_sql = dict(con.execute(consulta).fetchall())
        finally:
            con.close()

    def da_regra(self, caso):
        rotulo, _id, tem_pj, n, n_fem, n_masc, n_ind, n_nulo = caso
        if _id is None:
            classe = controle.classificar_com_base(0, 0, 0, False, 0)[0]
        else:
            classe = controle.classificar_com_base(
                n_fem, n_masc, n_ind, bool(tem_pj), n or 1, n_nulo)[0]
        return controle.rotulo_agregado(classe)

    def test_o_case_foi_encontrado_no_sql(self):
        self.assertIn("genero_controle",
                      construir_agregados.SQL_CONTROLE)
        self.assertIn("CASE", self.case_sql.upper())

    def test_regra_e_agregado_concordam_em_todos_os_casos(self):
        divergencias = []
        for caso in CASOS:
            rotulo = caso[0]
            esperado = self.da_regra(caso)
            obtido = self.do_sql[rotulo]
            if esperado != obtido:
                divergencias.append(f"{rotulo}: regra={esperado} agregado={obtido}")
        self.assertEqual(divergencias, [], "\n".join(divergencias))

    def test_socio_pj_nao_vira_controle_definido(self):
        """A cadeia societaria nao se resolve, entao nao ha maioria a declarar."""
        for rotulo in ("socio pj com quadro feminino",
                       "socio pj com quadro masculino"):
            self.assertEqual(self.do_sql[rotulo], "misto ou indeterminado")

    def test_empresa_sem_socio_tem_classe_propria(self):
        """A D5 manda declarar a parte, nao somar as mistas."""
        self.assertEqual(self.do_sql["sem linha de socio na base"],
                         "sem socio na base")
        self.assertNotEqual(self.do_sql["sem linha de socio na base"],
                            self.do_sql["empate"])

    def test_socio_sem_genero_nao_e_indeterminado(self):
        """Nulo e ausencia de veredito; indeterminado e veredito da RN-04."""
        self.assertEqual(self.do_sql["socio sem genero"], "nao classificado")
        self.assertNotEqual(self.do_sql["socio sem genero"],
                            self.do_sql["mais de um terco indeterm"])

    def test_socio_sem_genero_decide_antes_do_socio_pj(self):
        self.assertEqual(self.do_sql["socio sem genero e pj"],
                         "nao classificado")

    def test_so_feminino_e_masculino_contam_no_denominador(self):
        """Um terco exato de indeterminados ainda classifica; mais de um terco nao."""
        definidas = [r for r, c in self.do_sql.items()
                     if c in ("feminino", "masculino")]
        self.assertEqual(sorted(definidas), [
            "maioria feminina",
            "maioria masculina",
            "um terco exato de indeterm",
        ])
        self.assertEqual(self.do_sql["mais de um terco indeterm"],
                         "misto ou indeterminado")


if __name__ == "__main__":
    unittest.main()
