from pathlib import Path

from add_bus_marker import executar_add_bus_marker
from bdgd_extract import executar_extracao_ucbt
from add_ev import executar_add_ev
from search_segbt import executar_search_segbt
from odss_sim import executar_simulacoes_odss


def ler_quantidade_cargas() -> int:

    while True:
        valor = input(
            "Digite a quantidade de cargas EV que deseja criar: "
        ).strip()

        if not valor.isdigit():
            print("Informe apenas números inteiros.")
            continue

        quantidade = int(valor)

        if quantidade <= 0:
            print("A quantidade precisa ser maior que zero.")
            continue

        return quantidade


def main():

    gdb_path = Path(
        r"D:\py-dss-bdgd2dss"
        r"\Cemig-D_4950_2022-12-31_V11_20230920-1643.gdb"
    )

    # executar_extracao_ucbt(gdb_path=gdb_path,)

    ARQUIVO_MASTER_DSS = Path(
        r"C:\Users\Andre\Downloads\artigo\IJAU11"
        r"\Master_DU01_2022124950_IJAU11_--MBS-1--T--.dss"
    )

    quantidade_cargas = ler_quantidade_cargas()

    # executar_add_ev(quantidade=quantidade_cargas,)
    # executar_search_segbt()
    # executar_add_bus_marker()

    executar_simulacoes_odss(
        arquivo_dss=ARQUIVO_MASTER_DSS,
        quantidade_cargas_ev=quantidade_cargas,
        quantidade_simulacoes=2,
        horas_simulacao=[19, 20, 21, 22],
    )


if __name__ == "__main__":
    main()