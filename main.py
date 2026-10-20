from pathlib import Path

from add_bus_marker import executar_add_bus_marker
from bdgd_extract import executar_extracao_ucbt
from numero_veiculos import carregar_cenarios_eletrificacao
from odss_sim import executar_simulacoes_odss, gerar_cargas_ev_cenario

modo_numero_veiculos = "csv"  # "csv" ou "manual"

#----------------------------------------------------PARA A SIM CSV
niveis_eletrificacao = [20, 30, 40]
#----------------------------------------------------

#---------------------------------------------------- PARA A SIM MANUAL
quantidade_ldv = 30
quantidade_two_wheelers = 15
quantidade_trucks = 4
quantidade_buses = 0
#----------------------------------------------------

quantidade_simulacoes = 1
horas_simulacao = [20]

numero_simulacao_geracao = 1
seed_geracao = 10001

extrair_bdgd = False
gerar_cargas_ev = False
gerar_busmarker = False
simular = True

arquivo_cargas_ev_existente = None
arquivo_pv = None


def validar_hora_simulacao() -> float:
    if len(horas_simulacao) != 1:
        raise ValueError(
            "Informe apenas um horário em horas_simulacao."
        )

    try:
        hora_simulacao = float(horas_simulacao[0])
    except (TypeError, ValueError) as exc:
        raise ValueError("O horário da simulação deve ser numérico.") from exc

    if not 0 <= hora_simulacao < 24:
        raise ValueError("O horário da simulação deve estar entre 0 e 23.")

    return hora_simulacao


def imprimir_cenarios_eletrificacao(cenarios: list[dict]) -> None:
    print("")
    print("=" * 80)
    print("CENÁRIOS DE ELETRIFICAÇÃO CARREGADOS")
    print("=" * 80)

    for cenario in cenarios:
        print(
            f"{cenario['nivel_eletrificacao']:>2}% | "
            f"Hora: {cenario['hora_simulacao']:g}h | "
            f"LDV: {cenario['quantidade_ldv']} | "
            f"TW: {cenario['quantidade_two_wheelers']} | "
            f"Trucks: {cenario['quantidade_trucks']} | "
            f"Bus: {cenario['quantidade_buses']}"
        )

    print("=" * 80)


def executar_cenario_simulacao(
    arquivo_master_dss: Path,
    diretorio_dss_base: Path,
    diretorio_bdgd: Path,
    arquivos_extra_redirect: list[Path],
    quantidade_ldv_cenario: int,
    quantidade_two_wheelers_cenario: int,
    quantidade_trucks_cenario: int,
    quantidade_buses_cenario: int,
    identificador_cenario: str | None = None,
) -> None:
    executar_simulacoes_odss(
        arquivo_dss=arquivo_master_dss,
        diretorio_dss_base=diretorio_dss_base,
        diretorio_bdgd=diretorio_bdgd,
        arquivos_extra_redirect=arquivos_extra_redirect,
        quantidade_ldv=quantidade_ldv_cenario,
        quantidade_two_wheelers=quantidade_two_wheelers_cenario,
        quantidade_trucks=quantidade_trucks_cenario,
        quantidade_buses=quantidade_buses_cenario,
        quantidade_simulacoes=quantidade_simulacoes,
        horas_simulacao=horas_simulacao,
        salvar_arquivos_cenario=True,
        verbose_opendss_completo=True,
        identificador_cenario=identificador_cenario,
    )


def main():
    diretorio_codigo = Path(__file__).resolve().parent
    hora_simulacao = validar_hora_simulacao()

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

    if not simular:
        return

    modo = modo_numero_veiculos.strip().lower()

    if modo == "manual":
        executar_cenario_simulacao(
            arquivo_master_dss=arquivo_master_dss,
            diretorio_dss_base=diretorio_dss_base,
            diretorio_bdgd=diretorio_bdgd,
            arquivos_extra_redirect=arquivos_extra_redirect,
            quantidade_ldv_cenario=quantidade_ldv or 0,
            quantidade_two_wheelers_cenario=quantidade_two_wheelers or 0,
            quantidade_trucks_cenario=quantidade_trucks or 0,
            quantidade_buses_cenario=quantidade_buses or 0,
        )
        return

    if modo != "csv":
        raise ValueError(
            'modo_numero_veiculos deve ser "csv" ou "manual".'
        )

    cenarios = carregar_cenarios_eletrificacao(
        diretorio_codigo=diretorio_codigo,
        niveis_eletrificacao=niveis_eletrificacao,
        hora_simulacao=hora_simulacao,
    )
    imprimir_cenarios_eletrificacao(cenarios=cenarios,)

    for indice, cenario in enumerate(cenarios, start=1):
        nivel = cenario["nivel_eletrificacao"]

        print("")
        print("#" * 80)
        print(
            f"INICIANDO CENÁRIO {nivel}% "
            f"({indice}/{len(cenarios)})"
        )
        print(f"Arquivo: {cenario['arquivo_origem']}")
        print("#" * 80)

        executar_cenario_simulacao(
            arquivo_master_dss=arquivo_master_dss,
            diretorio_dss_base=diretorio_dss_base,
            diretorio_bdgd=diretorio_bdgd,
            arquivos_extra_redirect=arquivos_extra_redirect,
            quantidade_ldv_cenario=cenario["quantidade_ldv"],
            quantidade_two_wheelers_cenario=(
                cenario["quantidade_two_wheelers"]
            ),
            quantidade_trucks_cenario=cenario["quantidade_trucks"],
            quantidade_buses_cenario=cenario["quantidade_buses"],
            identificador_cenario=f"{nivel}pct",
        )


if __name__ == "__main__":
    main()
