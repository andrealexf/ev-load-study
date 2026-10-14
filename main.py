from pathlib import Path

from add_bus_marker import executar_add_bus_marker
from bdgd_extract import executar_extracao_ucbt
from odss_sim import executar_simulacoes_odss, gerar_cargas_ev_cenario

# 21 ; 40p	107t	306tw	3271ldv 	3bus
quantidade_ldv = 2464
quantidade_two_wheelers = 234
quantidade_trucks = 75
quantidade_buses = 2
quantidade_simulacoes = 500 #500
horas_simulacao = [21]

numero_simulacao_geracao = 1
seed_geracao = 10099

extrair_bdgd = False #false
gerar_cargas_ev = False #false
gerar_busmarker = False #false
simular = True #true

arquivo_cargas_ev_existente = None
arquivo_pv = None


def main():
    diretorio_codigo = Path(__file__).resolve().parent

    gdb_path = Path(
        r"D:\py-dss-bdgd2dss"
        r"\Cemig-D_4950_2022-12-31_V11_20230920-1643.gdb"
    ) #COLOCAR AQUI O DIRETÓRIO DA BDGD

    diretorio_bdgd = diretorio_codigo / "saida_bdgd_ucbt"
    diretorio_dss_base = diretorio_codigo / "DU01"
    diretorio_resultados_manual = diretorio_dss_base / "arquivos_gerados"
    diretorio_resultados_manual.mkdir(parents=True, exist_ok=True)

    arquivo_master_dss = diretorio_dss_base / "itajuba.dss"
    arquivo_cargas_ev = arquivo_cargas_ev_existente
    arquivos_extra_redirect = []

    if extrair_bdgd:
        executar_extracao_ucbt(
            gdb_path=gdb_path,
        )

    if gerar_cargas_ev and (
        quantidade_ldv is not None
        or quantidade_two_wheelers is not None
        or quantidade_trucks is not None
        or quantidade_buses is not None
    ):
        cenario_ev = gerar_cargas_ev_cenario(
            quantidade_ldv=quantidade_ldv or 0,
            quantidade_two_wheelers=quantidade_two_wheelers or 0,
            quantidade_trucks=quantidade_trucks or 0,
            quantidade_buses=quantidade_buses or 0,
            diretorio_dss_base=diretorio_dss_base,
            diretorio_bdgd=diretorio_bdgd,
            diretorio_resultados=diretorio_resultados_manual,
            numero_simulacao=numero_simulacao_geracao,
            seed_simulacao=seed_geracao,
        )

        arquivo_cargas_ev = cenario_ev["arquivo_cargas_ev"]

    if gerar_busmarker and arquivo_cargas_ev is not None:
        executar_add_bus_marker(
            arquivo_cargas_ev=arquivo_cargas_ev,
            diretorio_dss_base=diretorio_dss_base,
        )

    if arquivo_pv is not None:
        arquivos_extra_redirect.append(Path(arquivo_pv))

    if simular:
        executar_simulacoes_odss(
            arquivo_dss=arquivo_master_dss,
            diretorio_dss_base=diretorio_dss_base,
            diretorio_bdgd=diretorio_bdgd,
            arquivos_extra_redirect=arquivos_extra_redirect,
            quantidade_ldv=quantidade_ldv,
            quantidade_two_wheelers=quantidade_two_wheelers,
            quantidade_trucks=quantidade_trucks,
            quantidade_buses=quantidade_buses,
            quantidade_simulacoes=quantidade_simulacoes,
            horas_simulacao=horas_simulacao,
            salvar_arquivos_cenario=True,
            verbose_opendss_completo=True,
        )


if __name__ == "__main__":
    main()
