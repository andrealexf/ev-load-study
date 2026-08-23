from pathlib import Path
from datetime import datetime
import csv
import shutil
import time

try:
    from opendssdirect import dss
except ImportError:
    try:
        import opendssdirect as dss
    except ImportError as exc:
        raise ImportError(
            "O pacote OpenDSSDirect.py não está instalado.\n"
            "Execute no terminal:\n"
            'python -m pip install "OpenDSSDirect.py[extras]"'
        ) from exc

from add_ev import (
    executar_add_ev,
    ARQUIVO_SAIDA_EV as ARQUIVO_CARGAS_EV_ORIGEM,
)

from search_segbt import executar_search_segbt

from add_bus_marker import (
    executar_add_bus_marker,
    ARQUIVO_SAIDA as ARQUIVO_BUS_MARKERS_ORIGEM,
)


SEED_BASE_SIMULACAO = 10000
TENSAO_MINIMA_CONSIDERADA_PU = 0.4


def criar_diretorio_resultados(
    arquivo_dss: Path,
) -> Path:
    data_hora = datetime.now().strftime("%Y%m%d_%H%M%S")

    diretorio_resultados = (
        arquivo_dss.parent
        / f"simulacoes_odssdirect_{data_hora}"
    )

    diretorio_resultados.mkdir(
        parents=True,
        exist_ok=True,
    )

    return diretorio_resultados


def gerar_seed_simulacao(
    numero_simulacao: int,
) -> int:
    return SEED_BASE_SIMULACAO + numero_simulacao


def obter_ultimo_erro_dss() -> str:
    try:
        numero_erro = int(dss.Error.Number())
    except Exception:
        return ""

    if numero_erro == 0:
        return ""

    try:
        descricao = str(dss.Error.Description()).strip()
    except Exception:
        descricao = ""

    return f"Erro {numero_erro}: {descricao}"


def executar_comando_dss(
    comando: str,
    ignorar_erro: bool = False,
) -> str:
    try:
        resultado = dss.Text.Command(comando)
    except Exception as exc:
        if ignorar_erro:
            return ""

        raise RuntimeError(
            f"Erro ao executar comando DSS:\n{comando}"
        ) from exc

    mensagem_erro = obter_ultimo_erro_dss()

    if mensagem_erro and not ignorar_erro:
        raise RuntimeError(
            f"Erro retornado pelo DSS ao executar:\n"
            f"{comando}\n\n"
            f"{mensagem_erro}"
        )

    if resultado is None:
        return ""

    return str(resultado).strip()


def limpar_circuito() -> None:
    executar_comando_dss(
        comando="Clear",
    )


def executar_solve(
    hora_simulacao: float,
) -> bool:
    executar_comando_dss("Set Mode=Daily")
    executar_comando_dss("Set Number=1")
    executar_comando_dss("Set Stepsize=1h")
    executar_comando_dss(f"Set Hour={hora_simulacao}")

    dss.Solution.Solve()

    return bool(dss.Solution.Converged())


def preparar_cenario(
    numero_simulacao: int,
    quantidade_ldv: int,
    quantidade_two_wheelers: int,
    diretorio_resultados: Path,
) -> dict:
    seed_simulacao = gerar_seed_simulacao(
        numero_simulacao=numero_simulacao,
    )

    executar_add_ev(
        quantidade_ldv=quantidade_ldv,
        quantidade_two_wheelers=quantidade_two_wheelers,
        seed=seed_simulacao,
    )

    executar_search_segbt()

    executar_add_bus_marker()

    arquivo_cargas_ev_origem = Path(ARQUIVO_CARGAS_EV_ORIGEM).resolve()

    if not arquivo_cargas_ev_origem.exists():
        raise FileNotFoundError(
            f"Arquivo Cargas_EV não encontrado:\n"
            f"{arquivo_cargas_ev_origem}"
        )

    arquivo_bus_marker_origem = Path(ARQUIVO_BUS_MARKERS_ORIGEM).resolve()

    if not arquivo_bus_marker_origem.exists():
        raise FileNotFoundError(
            f"Arquivo de BusMarkers não encontrado:\n"
            f"{arquivo_bus_marker_origem}"
        )

    arquivo_cargas_ev_simulacao = (
        diretorio_resultados
        / f"Cargas_EV_Sim_{numero_simulacao:05d}_{seed_simulacao:05d}.dss"
    )

    arquivo_bus_marker_simulacao = (
        diretorio_resultados
        / f"BusMarkers_EV_Sim_{numero_simulacao:05d}_{seed_simulacao:05d}.dss"
    )

    shutil.copyfile(
        arquivo_cargas_ev_origem,
        arquivo_cargas_ev_simulacao,
    )

    shutil.copyfile(
        arquivo_bus_marker_origem,
        arquivo_bus_marker_simulacao,
    )

    return {
        "numero_simulacao": numero_simulacao,
        "seed_simulacao": seed_simulacao,
        "quantidade_ldv": quantidade_ldv,
        "quantidade_two_wheelers": quantidade_two_wheelers,
        "arquivo_cargas_ev": arquivo_cargas_ev_simulacao,
        "arquivo_bus_marker": arquivo_bus_marker_simulacao,
    }


def preparar_cenarios(
    quantidade_simulacoes: int,
    quantidade_ldv: int,
    quantidade_two_wheelers: int,
    diretorio_resultados: Path,
) -> list[dict]:
    cenarios = []

    for numero_simulacao in range(1, quantidade_simulacoes + 1):
        print("")
        print("=" * 80)
        print(f"PREPARANDO CENÁRIO {numero_simulacao:05d}/{quantidade_simulacoes:05d}")
        print("=" * 80)

        tempo_inicio = time.perf_counter()

        arquivos_cenario = preparar_cenario(
            numero_simulacao=numero_simulacao,
            quantidade_ldv=quantidade_ldv,
            quantidade_two_wheelers=quantidade_two_wheelers,
            diretorio_resultados=diretorio_resultados,
        )

        tempo_fim = time.perf_counter()

        arquivos_cenario["tempo_preparacao_segundos"] = (
            tempo_fim - tempo_inicio
        )

        cenarios.append(arquivos_cenario)

    return cenarios


def compilar_circuito_simulacao(
    arquivo_dss: Path,
    arquivo_cargas_ev: Path,
    arquivo_bus_marker: Path,
) -> None:
    arquivo_dss = Path(arquivo_dss).resolve()
    arquivo_cargas_ev = Path(arquivo_cargas_ev).resolve()
    arquivo_bus_marker = Path(arquivo_bus_marker).resolve()

    if not arquivo_dss.exists():
        raise FileNotFoundError(
            f"Arquivo Master do OpenDSS não encontrado:\n{arquivo_dss}"
        )

    if not arquivo_cargas_ev.exists():
        raise FileNotFoundError(
            f"Arquivo Cargas_EV da simulação não encontrado:\n"
            f"{arquivo_cargas_ev}"
        )

    if not arquivo_bus_marker.exists():
        raise FileNotFoundError(
            f"Arquivo BusMarker da simulação não encontrado:\n"
            f"{arquivo_bus_marker}"
        )

    limpar_circuito()

    executar_comando_dss(
        comando=f'Compile "{arquivo_dss}"',
    )

    quantidade_barras = int(dss.Circuit.NumBuses())

    if quantidade_barras <= 0:
        raise RuntimeError(
            "O arquivo foi processado, mas nenhum circuito foi carregado."
        )

    executar_comando_dss(
        comando=f'Redirect "{arquivo_cargas_ev}"',
    )

    executar_comando_dss(
        comando="ClearBusMarkers",
        ignorar_erro=True,
    )

    executar_comando_dss(
        comando=f'Redirect "{arquivo_bus_marker}"',
        ignorar_erro=True,
    )


def obter_tensoes_validas(
    limite_minimo_pu: float = TENSAO_MINIMA_CONSIDERADA_PU,
) -> list[float]:
    try:
        tensoes = list(dss.Circuit.AllBusMagPu() or [])
    except Exception:
        tensoes = []

    tensoes_validas = []

    for tensao in tensoes:
        if tensao is None:
            continue

        valor = float(tensao)

        if valor < limite_minimo_pu:
            continue

        tensoes_validas.append(valor)

    return tensoes_validas


def obter_quantidade_nos() -> int:
    try:
        return int(dss.Circuit.NumNodes())
    except Exception:
        try:
            return len(list(dss.Circuit.AllNodeNames() or []))
        except Exception:
            return 0


def obter_nome_circuito() -> str:
    try:
        return str(dss.Circuit.Name())
    except Exception:
        return ""


def coletar_resumo_simulacao(
    simulacao_global: int,
    total_execucoes: int,
    numero_simulacao: int,
    seed_simulacao: int,
    quantidade_simulacoes: int,
    quantidade_ldv: int,
    quantidade_two_wheelers: int,
    hora_simulacao: float,
    arquivo_cargas_ev: Path,
    arquivo_bus_marker: Path,
    tempo_preparacao_segundos: float,
    tempo_compilacao_segundos: float,
    tempo_solve_segundos: float,
) -> dict:
    try:
        potencia_total = list(dss.Circuit.TotalPower() or [0.0, 0.0])
    except Exception:
        potencia_total = [0.0, 0.0]

    try:
        perdas = list(dss.Circuit.Losses() or [0.0, 0.0])
    except Exception:
        perdas = [0.0, 0.0]

    potencia_total_kw = abs(float(potencia_total[0]))
    potencia_total_kvar = abs(float(potencia_total[1]))

    perdas_kw = abs(float(perdas[0])) / 1000
    perdas_kvar = abs(float(perdas[1])) / 1000

    potencia_total_mw = potencia_total_kw / 1000
    potencia_total_mvar = potencia_total_kvar / 1000

    perdas_mw = perdas_kw / 1000
    perdas_mvar = perdas_kvar / 1000

    if potencia_total_kw > 0:
        perdas_percentual = perdas_kw / potencia_total_kw * 100
    else:
        perdas_percentual = 0.0

    tensoes_validas = obter_tensoes_validas(
        limite_minimo_pu=TENSAO_MINIMA_CONSIDERADA_PU,
    )

    tensao_minima = (
        min(tensoes_validas)
        if tensoes_validas
        else 0.0
    )

    tensao_maxima = (
        max(tensoes_validas)
        if tensoes_validas
        else 0.0
    )

    try:
        iteracoes = int(dss.Solution.MostIterationsDone())
    except Exception:
        iteracoes = 0

    quantidade_total_ev = quantidade_ldv + quantidade_two_wheelers

    return {
        "simulacao": simulacao_global,
        "total_execucoes": total_execucoes,
        "simulacao_horario": numero_simulacao,
        "seed_simulacao": seed_simulacao,
        "simulacoes_por_horario": quantidade_simulacoes,
        "quantidade_ldv": quantidade_ldv,
        "quantidade_two_wheelers": quantidade_two_wheelers,
        "quantidade_total_ev": quantidade_total_ev,
        "hora_simulacao": hora_simulacao,
        "circuito": obter_nome_circuito(),
        "convergiu": bool(dss.Solution.Converged()),
        "quantidade_barras": int(dss.Circuit.NumBuses()),
        "quantidade_nos": obter_quantidade_nos(),

        "potencia_total_kw": potencia_total_kw,
        "potencia_total_kvar": potencia_total_kvar,
        "potencia_total_mw": potencia_total_mw,
        "potencia_total_mvar": potencia_total_mvar,

        "perdas_kw": perdas_kw,
        "perdas_kvar": perdas_kvar,
        "perdas_mw": perdas_mw,
        "perdas_mvar": perdas_mvar,
        "perdas_percentual": perdas_percentual,

        "tensao_minima_pu": tensao_minima,
        "tensao_maxima_pu": tensao_maxima,
        "iteracoes": iteracoes,

        "tempo_preparacao_segundos": tempo_preparacao_segundos,
        "tempo_compilacao_segundos": tempo_compilacao_segundos,
        "tempo_solve_segundos": tempo_solve_segundos,

        "arquivo_cargas_ev": str(arquivo_cargas_ev),
        "arquivo_bus_marker": str(arquivo_bus_marker),
    }


def colunas_resultado() -> list[str]:
    return [
        "simulacao",
        "total_execucoes",
        "simulacao_horario",
        "seed_simulacao",
        "simulacoes_por_horario",
        "quantidade_ldv",
        "quantidade_two_wheelers",
        "quantidade_total_ev",
        "hora_simulacao",
        "circuito",
        "convergiu",
        "quantidade_barras",
        "quantidade_nos",

        "potencia_total_kw",
        "potencia_total_kvar",
        "potencia_total_mw",
        "potencia_total_mvar",

        "perdas_kw",
        "perdas_kvar",
        "perdas_mw",
        "perdas_mvar",
        "perdas_percentual",

        "tensao_minima_pu",
        "tensao_maxima_pu",
        "iteracoes",

        "tempo_preparacao_segundos",
        "tempo_compilacao_segundos",
        "tempo_solve_segundos",

        "arquivo_cargas_ev",
        "arquivo_bus_marker",
    ]


def salvar_checkpoint_resultado(
    resultado: dict,
    arquivo_checkpoint: Path,
) -> None:
    arquivo_existe = arquivo_checkpoint.exists()

    colunas = colunas_resultado()

    with open(
        arquivo_checkpoint,
        "a",
        encoding="utf-8-sig",
        newline="",
    ) as arquivo:
        writer = csv.DictWriter(
            arquivo,
            fieldnames=colunas,
            delimiter=";",
        )

        if not arquivo_existe:
            writer.writeheader()

        writer.writerow(
            {
                coluna: resultado[coluna]
                for coluna in colunas
            }
        )


def salvar_resumo_simulacoes(
    resultados: list[dict],
    diretorio_resultados: Path,
) -> Path:
    arquivo_saida = (
        diretorio_resultados
        / "Resumo_Simulacoes_OpenDSSDirect.csv"
    )

    colunas = colunas_resultado()

    with open(
        arquivo_saida,
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as arquivo:
        writer = csv.DictWriter(
            arquivo,
            fieldnames=colunas,
            delimiter=";",
        )

        writer.writeheader()

        for resultado in resultados:
            writer.writerow(
                {
                    coluna: resultado[coluna]
                    for coluna in colunas
                }
            )

    return arquivo_saida


def imprimir_cabecalho(
    arquivo_dss: Path,
    quantidade_ldv: int,
    quantidade_two_wheelers: int,
    quantidade_simulacoes: int,
    diretorio_resultados: Path,
    horas_simulacao: list[float],
) -> None:
    quantidade_total_ev = quantidade_ldv + quantidade_two_wheelers

    print("=" * 80)
    print("SIMULAÇÕES OPENDSSDIRECT.PY")
    print("=" * 80)
    print(f"Arquivo Master: {arquivo_dss}")
    print(f"LDVs por cenário: {quantidade_ldv}")
    print(f"Two Wheelers por cenário: {quantidade_two_wheelers}")
    print(f"Total EV por cenário: {quantidade_total_ev}")
    print(f"Quantidade de cenários: {quantidade_simulacoes}")
    print(f"Horários simulados: {horas_simulacao}")
    print(f"Total de execuções elétricas: {quantidade_simulacoes * len(horas_simulacao)}")
    print(f"Diretório de resultados: {diretorio_resultados}")
    print("Em cada execução será aplicado:")
    print("- Redirect do Cargas_EV_Sim_XXXXX_SEED.dss")
    print("- Redirect do BusMarkers_EV_Sim_XXXXX_SEED.dss")
    print("=" * 80)


def imprimir_summary_opendss(
    resultado: dict,
) -> None:
    print("")
    print(
        f'SUMMARY OPENDSS - '
        f'Hora {resultado["hora_simulacao"]:.0f}h - '
        f'Simulação {resultado["simulacao_horario"]:05d}/'
        f'{resultado["simulacoes_por_horario"]:05d} - '
        f'Seed {resultado["seed_simulacao"]:05d} - '
        f'Execução {resultado["simulacao"]:05d}/'
        f'{resultado["total_execucoes"]:05d}'
    )
    print("-" * 80)
    print(f'Hour = {resultado["hora_simulacao"]:.6g}')
    print(f'Max pu. voltage = {resultado["tensao_maxima_pu"]:.6g}')
    print(f'Min pu. voltage = {resultado["tensao_minima_pu"]:.6g}')
    print(
        "Total Active Power:   "
        f'{resultado["potencia_total_mw"]:.6f} MW'
    )
    print(
        "Total Reactive Power: "
        f'{resultado["potencia_total_mvar"]:.6f} Mvar'
    )
    print(
        "Total Active Losses:   "
        f'{resultado["perdas_mw"]:.6f} MW, '
        f'({resultado["perdas_percentual"]:.3f} %)'
    )
    print(
        "Total Reactive Losses: "
        f'{resultado["perdas_mvar"]:.6f} Mvar'
    )
    print("-" * 80)


def imprimir_andamento(
    resultado: dict,
    total_execucoes: int,
) -> None:
    print(
        f'Simulação {resultado["simulacao"]:05d}/{total_execucoes:05d} | '
        f'Hora: {resultado["hora_simulacao"]:.0f}h | '
        f'Cenário: {resultado["simulacao_horario"]:05d}/'
        f'{resultado["simulacoes_por_horario"]:05d} | '
        f'Seed: {resultado["seed_simulacao"]:05d} | '
        f'LDV: {resultado["quantidade_ldv"]} | '
        f'Two Wheelers: {resultado["quantidade_two_wheelers"]} | '
        f'Convergiu: {"SIM" if resultado["convergiu"] else "NÃO"} | '
        f'Tensão min: {resultado["tensao_minima_pu"]:.6f} pu | '
        f'Tensão max: {resultado["tensao_maxima_pu"]:.6f} pu | '
        f'Perdas: {resultado["perdas_kw"]:.6f} kW | '
        f'Perdas %: {resultado["perdas_percentual"]:.3f}% | '
        f'Prep: {resultado["tempo_preparacao_segundos"]:.3f}s | '
        f'Compile+Redirect: {resultado["tempo_compilacao_segundos"]:.3f}s | '
        f'Solve: {resultado["tempo_solve_segundos"]:.3f}s'
    )

    imprimir_summary_opendss(
        resultado=resultado,
    )

    print("")
    print("=" * 150, " - fim")
    print("")


def imprimir_resumo_final(
    resultados: list[dict],
    arquivo_resumo: Path,
    arquivo_checkpoint: Path,
    tempo_total_segundos: float,
) -> None:
    total = len(resultados)

    total_convergente = sum(
        1
        for resultado in resultados
        if resultado["convergiu"]
    )

    total_nao_convergente = total - total_convergente

    if resultados:
        menor_tensao = min(
            resultado["tensao_minima_pu"]
            for resultado in resultados
        )

        maior_tensao = max(
            resultado["tensao_maxima_pu"]
            for resultado in resultados
        )

        maior_perda = max(
            resultado["perdas_kw"]
            for resultado in resultados
        )

        tempo_medio_preparacao = sum(
            resultado["tempo_preparacao_segundos"]
            for resultado in resultados
        ) / total

        tempo_medio_compilacao = sum(
            resultado["tempo_compilacao_segundos"]
            for resultado in resultados
        ) / total

        tempo_medio_solve = sum(
            resultado["tempo_solve_segundos"]
            for resultado in resultados
        ) / total
    else:
        menor_tensao = 0.0
        maior_tensao = 0.0
        maior_perda = 0.0
        tempo_medio_preparacao = 0.0
        tempo_medio_compilacao = 0.0
        tempo_medio_solve = 0.0

    simulacoes_por_segundo = (
        total / tempo_total_segundos
        if tempo_total_segundos > 0
        else 0.0
    )

    print("\n" + "=" * 80)
    print("SIMULAÇÕES FINALIZADAS")
    print("=" * 80)
    print(f"Total de execuções elétricas: {total}")
    print(f"Convergentes: {total_convergente}")
    print(f"Não convergentes: {total_nao_convergente}")
    print(f"Menor tensão encontrada: {menor_tensao:.6f} pu")
    print(f"Maior tensão encontrada: {maior_tensao:.6f} pu")
    print(f"Maior perda encontrada: {maior_perda:.6f} kW")
    print(f"Tempo médio preparação: {tempo_medio_preparacao:.6f} s")
    print(f"Tempo médio compile/redirect: {tempo_medio_compilacao:.6f} s")
    print(f"Tempo médio solve: {tempo_medio_solve:.6f} s")
    print(f"Tempo total: {tempo_total_segundos:.2f} segundos")
    print(f"Execuções por segundo: {simulacoes_por_segundo:.4f}")
    print(f"Arquivo resumo final: {arquivo_resumo}")
    print(f"Arquivo checkpoint: {arquivo_checkpoint}")
    print("=" * 80)


def executar_simulacoes_odss(
    arquivo_dss: Path,
    quantidade_ldv: int,
    quantidade_two_wheelers: int,
    quantidade_simulacoes: int = 6000,
    horas_simulacao: list[float] | None = None,
) -> list[dict]:
    arquivo_dss = Path(arquivo_dss).resolve()

    if horas_simulacao is None:
        horas_simulacao = [19, 20, 21, 22]

    if not arquivo_dss.exists():
        raise FileNotFoundError(
            f"Arquivo Master do OpenDSS não encontrado:\n{arquivo_dss}"
        )

    if quantidade_ldv < 0:
        raise ValueError("A quantidade de LDVs não pode ser negativa.")

    if quantidade_two_wheelers < 0:
        raise ValueError("A quantidade de Two Wheelers não pode ser negativa.")

    if quantidade_ldv + quantidade_two_wheelers <= 0:
        raise ValueError(
            "A soma de LDVs e Two Wheelers precisa ser maior que zero."
        )

    if quantidade_simulacoes <= 0:
        raise ValueError(
            "A quantidade de simulações precisa ser maior que zero."
        )

    if not horas_simulacao:
        raise ValueError(
            "Informe pelo menos um horário de simulação."
        )

    diretorio_resultados = criar_diretorio_resultados(
        arquivo_dss=arquivo_dss,
    )

    arquivo_checkpoint = (
        diretorio_resultados
        / "Checkpoint_Simulacoes_OpenDSSDirect.csv"
    )

    total_execucoes = quantidade_simulacoes * len(horas_simulacao)

    imprimir_cabecalho(
        arquivo_dss=arquivo_dss,
        quantidade_ldv=quantidade_ldv,
        quantidade_two_wheelers=quantidade_two_wheelers,
        quantidade_simulacoes=quantidade_simulacoes,
        diretorio_resultados=diretorio_resultados,
        horas_simulacao=horas_simulacao,
    )

    tempo_inicio_total = time.perf_counter()

    cenarios = preparar_cenarios(
        quantidade_simulacoes=quantidade_simulacoes,
        quantidade_ldv=quantidade_ldv,
        quantidade_two_wheelers=quantidade_two_wheelers,
        diretorio_resultados=diretorio_resultados,
    )

    resultados = []

    simulacao_global = 0

    for hora_simulacao in horas_simulacao:
        print("")
        print("=" * 80)
        print(f"INICIANDO SIMULAÇÕES PARA {hora_simulacao:.0f}h")
        print("=" * 80)

        for cenario in cenarios:
            simulacao_global += 1

            numero_simulacao = cenario["numero_simulacao"]
            seed_simulacao = cenario["seed_simulacao"]
            quantidade_ldv_cenario = cenario["quantidade_ldv"]
            quantidade_two_wheelers_cenario = cenario["quantidade_two_wheelers"]
            arquivo_cargas_ev = cenario["arquivo_cargas_ev"]
            arquivo_bus_marker = cenario["arquivo_bus_marker"]
            tempo_preparacao = cenario["tempo_preparacao_segundos"]

            tempo_inicio_compilacao = time.perf_counter()

            compilar_circuito_simulacao(
                arquivo_dss=arquivo_dss,
                arquivo_cargas_ev=arquivo_cargas_ev,
                arquivo_bus_marker=arquivo_bus_marker,
            )

            tempo_fim_compilacao = time.perf_counter()

            tempo_inicio_solve = time.perf_counter()

            executar_solve(
                hora_simulacao=hora_simulacao,
            )

            tempo_fim_solve = time.perf_counter()

            resultado = coletar_resumo_simulacao(
                simulacao_global=simulacao_global,
                total_execucoes=total_execucoes,
                numero_simulacao=numero_simulacao,
                seed_simulacao=seed_simulacao,
                quantidade_simulacoes=quantidade_simulacoes,
                quantidade_ldv=quantidade_ldv_cenario,
                quantidade_two_wheelers=quantidade_two_wheelers_cenario,
                hora_simulacao=hora_simulacao,
                arquivo_cargas_ev=arquivo_cargas_ev,
                arquivo_bus_marker=arquivo_bus_marker,
                tempo_preparacao_segundos=tempo_preparacao,
                tempo_compilacao_segundos=(
                    tempo_fim_compilacao
                    - tempo_inicio_compilacao
                ),
                tempo_solve_segundos=(
                    tempo_fim_solve
                    - tempo_inicio_solve
                ),
            )

            resultados.append(resultado)

            salvar_checkpoint_resultado(
                resultado=resultado,
                arquivo_checkpoint=arquivo_checkpoint,
            )

            if (
                simulacao_global <= 10
                or simulacao_global == total_execucoes
                or simulacao_global % 100 == 0
            ):
                imprimir_andamento(
                    resultado=resultado,
                    total_execucoes=total_execucoes,
                )

    arquivo_resumo = salvar_resumo_simulacoes(
        resultados=resultados,
        diretorio_resultados=diretorio_resultados,
    )

    tempo_total_segundos = (
        time.perf_counter()
        - tempo_inicio_total
    )

    imprimir_resumo_final(
        resultados=resultados,
        arquivo_resumo=arquivo_resumo,
        arquivo_checkpoint=arquivo_checkpoint,
        tempo_total_segundos=tempo_total_segundos,
    )

    return resultados


def executar_odss_sim(
    arquivo_dss: Path,
) -> dict:
    resultados = executar_simulacoes_odss(
        arquivo_dss=arquivo_dss,
        quantidade_ldv=1,
        quantidade_two_wheelers=0,
        quantidade_simulacoes=1,
        horas_simulacao=[19],
    )

    return resultados[0]