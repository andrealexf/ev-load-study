from pathlib import Path

from add_bus_marker import executar_add_bus_marker
from bdgd_extract import executar_extracao_ucbt
from add_ev import executar_add_ev
from search_segbt import executar_search_segbt
from odss_sim import executar_simulacoes_odss


def ler_quantidade_veiculo(
    descricao: str,
) -> int:

    while True:
        valor = input(
            f"Digite a quantidade de {descricao} que deseja criar: "
        ).strip()

        if not valor.isdigit():
            print("Informe apenas números inteiros.")
            continue

        quantidade = int(valor)

        if quantidade < 0:
            print("A quantidade não pode ser negativa.")
            continue

        return quantidade


def ler_quantidades_cargas() -> tuple[int, int]:

    while True:
        quantidade_ldv = ler_quantidade_veiculo(
            "LDVs (Light-Duty Vehicles)"
        )

        quantidade_two_wheelers = ler_quantidade_veiculo(
            "Two Wheelers"
        )

        if quantidade_ldv + quantidade_two_wheelers <= 0:
            print(
                "A soma de LDVs e Two Wheelers precisa ser maior que zero."
            )
            continue

        return quantidade_ldv, quantidade_two_wheelers


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

    quantidade_ldv, quantidade_two_wheelers = ler_quantidades_cargas()

    # executar_add_ev(quantidade_ldv=quantidade_ldv,quantidade_two_wheelers=quantidade_two_wheelers,)
    #executar_search_segbt()
    #executar_add_bus_marker()
    executar_simulacoes_odss(
        arquivo_dss=ARQUIVO_MASTER_DSS,
        quantidade_ldv=quantidade_ldv,
        quantidade_two_wheelers=quantidade_two_wheelers,
        quantidade_simulacoes=2,
        horas_simulacao=[19]#, 20, 21, 22],
    )


if __name__ == "__main__":
    main()