from pathlib import Path

from add_bus_marker import executar_add_bus_marker
from bdgd_extract import executar_extracao_ucbt
from odss_sim import executar_simulacoes_odss, gerar_cargas_ev_cenario


quantidade_ldv = 30
quantidade_two_wheelers = 30
quantidade_simulacoes = 1
horas_simulacao = [19]
numero_simulacao_geracao = 1
seed_geracao = 10001

extrair_bdgd = False
gerar_cargas_ev = True
gerar_busmarker = True
simular = False

arquivo_cargas_ev_existente = None
arquivo_pv = None


def main():
    diretorio_codigo = Path(__file__).resolve().parent

    gdb_path = Path(
        r"D:\py-dss-bdgd2dss"
        r"\Cemig-D_4950_2022-12-31_V11_20230920-1643.gdb"
    )

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
    ):
        cenario_ev = gerar_cargas_ev_cenario(
            quantidade_ldv=quantidade_ldv or 0,
            quantidade_two_wheelers=quantidade_two_wheelers or 0,
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
        arquivos_extra_redirect.append(
            Path(arquivo_pv)
        )

    if simular:
        executar_simulacoes_odss(
            arquivo_dss=arquivo_master_dss,
            diretorio_dss_base=diretorio_dss_base,
            diretorio_bdgd=diretorio_bdgd,
            arquivo_cargas_ev=arquivo_cargas_ev,
            arquivos_extra_redirect=arquivos_extra_redirect,
            quantidade_ldv=quantidade_ldv,
            quantidade_two_wheelers=quantidade_two_wheelers,
            quantidade_simulacoes=quantidade_simulacoes,
            horas_simulacao=horas_simulacao,
        )


if __name__ == "__main__":
    main()