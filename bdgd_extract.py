from pathlib import Path

from bdgd_functions import gerar_json_brr_pac_por_bairro


alimentadores = [
    "IJAU05",
    "IJAU06",
    "IJAU07",
    "IJAU10",
    "IJAU11",
    "IJAU13",
    "IJAU14",
    "IJAU15",
]


classes_ucbt = [
    {"nome": "RE","prefixo": "RE",},
    {"nome": "IN","prefixo": "IN",},
]


def executar_extracao_ucbt(
    gdb_path: Path,
) -> None:
    diretorio_codigo = Path(__file__).resolve().parent
    diretorio_saida = diretorio_codigo / "saida_bdgd_ucbt"
    diretorio_saida.mkdir(parents=True, exist_ok=True)

    for classe in classes_ucbt:
        nome_classe = classe["nome"]
        prefixo_classe = classe["prefixo"]

        for alimentador in alimentadores:
            arquivo_loads_txt = diretorio_saida / f"Loads_UCBT_{nome_classe}_{alimentador}.txt"
            arquivo_json = diretorio_saida / f"ucbt_{nome_classe}_{alimentador}_BRR_PAC.json"
            arquivo_diagnostico_csv = diretorio_saida / f"Diagnostico_UCBT_{nome_classe}_{alimentador}.csv"

            gerar_json_brr_pac_por_bairro(
                gdb_path=gdb_path,
                arquivo_loads_dss=arquivo_loads_txt,
                camada_ucbt="UCBT_tab",
                ctmt_filtro=alimentador,
                clas_sub_prefixo=prefixo_classe,
                arquivo_json=arquivo_json,
                garantir_pac_10_digitos=True,
                arquivo_diagnostico_csv=arquivo_diagnostico_csv,
            )