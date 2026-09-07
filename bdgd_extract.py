from pathlib import Path

from bdgd_functions import gerar_json_brr_pac_por_bairro


ALIMENTADORES = [
    "IJAU05",
    "IJAU06",
    "IJAU07",
    "IJAU10",
    "IJAU11",
    "IJAU13",
    "IJAU14",
    "IJAU15",
]


def executar_extracao_ucbt(
    gdb_path: Path,
) -> None:
    diretorio_codigo = Path(__file__).resolve().parent

    diretorio_saida = diretorio_codigo / "saida_bdgd_ucbt"

    diretorio_saida.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 80)
    print("EXTRAÇÃO UCBT PARA MÚLTIPLOS ALIMENTADORES")
    print("=" * 80)
    print(f"GDB: {gdb_path}")
    print(f"Diretório de saída: {diretorio_saida}")
    print(f"Alimentadores: {', '.join(ALIMENTADORES)}")
    print("=" * 80)

    for alimentador in ALIMENTADORES:
        print("")
        print("#" * 80)
        print(f"INICIANDO EXTRAÇÃO DO ALIMENTADOR {alimentador}")
        print("#" * 80)

        arquivo_loads_txt = (
            diretorio_saida
            / f"Loads_UCBT_{alimentador}.txt"
        )

        arquivo_json = (
            diretorio_saida
            / f"ucbt_{alimentador}_BRR_PAC.json"
        )

        arquivo_diagnostico_csv = (
            diretorio_saida
            / f"Diagnostico_UCBT_{alimentador}.csv"
        )

        try:
            gerar_json_brr_pac_por_bairro(
                gdb_path=gdb_path,
                arquivo_loads_dss=arquivo_loads_txt,
                camada_ucbt="UCBT_tab",
                ctmt_filtro=alimentador,
                clas_sub_prefixo="RE",
                arquivo_json=arquivo_json,
                garantir_pac_10_digitos=True,
                arquivo_diagnostico_csv=arquivo_diagnostico_csv,
            )

            print("")
            print(f"Extração finalizada para {alimentador}")
            print(f"Arquivo ramais: {arquivo_loads_txt}")
            print(f"Arquivo JSON: {arquivo_json}")
            print(f"Arquivo diagnóstico: {arquivo_diagnostico_csv}")

        except Exception as exc:
            print("")
            print("=" * 80)
            print(f"ERRO AO EXTRAIR ALIMENTADOR {alimentador}")
            print("=" * 80)
            print(exc)
            print("=" * 80)

    print("")
    print("=" * 80)
    print("EXTRAÇÃO EM LOTE FINALIZADA")
    print("=" * 80)
    print(f"Arquivos gerados em: {diretorio_saida}")
    print("=" * 80)