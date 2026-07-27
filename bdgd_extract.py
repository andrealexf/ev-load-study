from pathlib import Path

from bdgd_functions import gerar_json_brr_pac_por_bairro


def executar_extracao_ucbt(
    gdb_path: Path,
) -> None:

    diretorio_codigo = Path(__file__).resolve().parent

    # Arquivos criados no mesmo diretório do código
    arquivo_loads_dss = diretorio_codigo / "Loads_UCBT_IJAU11.dss"

    arquivo_json = diretorio_codigo / "ucbt_IJAU11_BRR_PAC.json"

    gerar_json_brr_pac_por_bairro(
        gdb_path=gdb_path,
        arquivo_loads_dss=arquivo_loads_dss,
        camada_ucbt="UCBT_tab",
        ctmt_filtro="IJAU11",
        clas_sub_prefixo="RE",
        arquivo_json=arquivo_json,
    )


if __name__ == "__main__":
    executar_extracao_ucbt()