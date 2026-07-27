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

from add_ev import executar_add_ev
from search_segbt import executar_search_segbt
from add_bus_marker import (executar_add_bus_marker,ARQUIVO_SAIDA as ARQUIVO_BUS_MARKERS_ORIGEM,)


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


def compilar_circuito_base(
    arquivo_dss: Path,
) -> None:
    arquivo_dss = Path(arquivo_dss).resolve()

    if not arquivo_dss.exists():
        raise FileNotFoundError(
            f"Arquivo Master do OpenDSS não encontrado:\n{arquivo_dss}"
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


def preparar_cenario(
    numero_simulacao: int,
    quantidade_cargas_ev: int,
    diretorio_resultados: Path,
) -> Path:
    executar_add_ev(
        quantidade=quantidade_cargas_ev,
    )

    executar_search_segbt()

    executar_add_bus_marker()

    arquivo_origem = Path(ARQUIVO_BUS_MARKERS_ORIGEM).resolve()

    if not arquivo_origem.exists():
        raise FileNotFoundError(
            f"Arquivo de BusMarkers não encontrado:\n{arquivo_origem}"
        )

    arquivo_bus_marker_simulacao = (
        diretorio_resultados
        / f"BusMarkers_EV_Sim_{numero_simulacao:05d}.dss"
    )

    shutil.copyfile(
        arquivo_origem,
        arquivo_bus_marker_simulacao,
    )

    return arquivo_bus_marker_simulacao


def limpar_bus_markers() -> None:
    executar_comando_dss(
        comando="ClearBusMarkers",
        ignorar_erro=True,
    )


def aplicar_redirect_bus_marker(
    arquivo_bus_marker: Path,
) -> None:
    arquivo_bus_marker = Path(arquivo_bus_marker).resolve()

    if not arquivo_bus_marker.exists():
        raise FileNotFoundError(
            f"Arquivo BusMarker da simulação não encontrado:\n"
            f"{arquivo_bus_marker}"
        )

    limpar_bus_markers()

    executar_comando_dss(
        comando=f'Redirect "{arquivo_bus_marker}"',
        ignorar_erro=True,
    )


def executar_solve() -> bool:
    dss.Solution.Solve()

    return bool(dss.Solution.Converged())


def obter_tensoes_validas() -> list[float]:
    try:
        tensoes = list(dss.Circuit.AllBusMagPu() or [])
    except Exception:
        tensoes = []

    tensoes_validas = []

    for tensao in tensoes:
        if tensao is None:
            continue

        valor = float(tensao)

        if valor <= 0:
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
    numero_simulacao: int,
    arquivo_bus_marker: Path,
    tempo_preparacao_segundos: float,
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

    tensoes_validas = obter_tensoes_validas()

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

    return {
        "simulacao": numero_simulacao,
        "circuito": obter_nome_circuito(),
        "convergiu": bool(dss.Solution.Converged()),
        "quantidade_barras": int(dss.Circuit.NumBuses()),
        "quantidade_nos": obter_quantidade_nos(),
        "potencia_total_kw": float(potencia_total[0]),
        "potencia_total_kvar": float(potencia_total[1]),
        "perdas_kw": float(perdas[0]) / 1000,
        "perdas_kvar": float(perdas[1]) / 1000,
        "tensao_minima_pu": tensao_minima,
        "tensao_maxima_pu": tensao_maxima,
        "iteracoes": iteracoes,
        "tempo_preparacao_segundos": tempo_preparacao_segundos,
        "tempo_solve_segundos": tempo_solve_segundos,
        "arquivo_bus_marker": str(arquivo_bus_marker),
    }


def salvar_checkpoint_resultado(
    resultado: dict,
    arquivo_checkpoint: Path,
) -> None:
    arquivo_existe = arquivo_checkpoint.exists()

    colunas = [
        "simulacao",
        "circuito",
        "convergiu",
        "quantidade_barras",
        "quantidade_nos",
        "potencia_total_kw",
        "potencia_total_kvar",
        "perdas_kw",
        "perdas_kvar",
        "tensao_minima_pu",
        "tensao_maxima_pu",
        "iteracoes",
        "tempo_preparacao_segundos",
        "tempo_solve_segundos",
        "arquivo_bus_marker",
    ]

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

    colunas = [
        "simulacao",
        "circuito",
        "convergiu",
        "quantidade_barras",
        "quantidade_nos",
        "potencia_total_kw",
        "potencia_total_kvar",
        "perdas_kw",
        "perdas_kvar",
        "tensao_minima_pu",
        "tensao_maxima_pu",
        "iteracoes",
        "tempo_preparacao_segundos",
        "tempo_solve_segundos",
        "arquivo_bus_marker",
    ]

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
    quantidade_cargas_ev: int,
    quantidade_simulacoes: int,
    diretorio_resultados: Path,
) -> None:
    print("=" * 80)
    '''
    print("SIMULAÇÕES OPENDSSDIRECT.PY")
    print("=" * 80)
    print("Método: OpenDSSDirect.py / DSS-Extensions")
    print("Uso de COM: NÃO")
    print("Necessita OpenDSS instalado via COM: NÃO")
    print(f"Arquivo Master: {arquivo_dss}")
    print(f"Quantidade de cargas EV por cenário: {quantidade_cargas_ev}")
    print(f"Quantidade de simulações: {quantidade_simulacoes}")
    print(f"Diretório de resultados: {diretorio_resultados}")
    print("O circuito base será compilado apenas uma vez.")
    print("Em cada cenário será aplicado apenas o Redirect do BusMarkers.")
    print("=" * 80)
    '''

def imprimir_andamento(
    resultado: dict,
    quantidade_simulacoes: int,
) -> None:
    simulacao = resultado["simulacao"]

    print(
        f'Simulação {simulacao:05d}/{quantidade_simulacoes:05d} | '
        f'Convergiu: {"SIM" if resultado["convergiu"] else "NÃO"} | '
        f'Tensão min: {resultado["tensao_minima_pu"]:.6f} pu | '
        f'Tensão max: {resultado["tensao_maxima_pu"]:.6f} pu | '
        f'Perdas: {resultado["perdas_kw"]:.6f} kW | '
        f'Prep: {resultado["tempo_preparacao_segundos"]:.3f}s | '
        f'Solve: {resultado["tempo_solve_segundos"]:.3f}s'
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

        tempo_medio_solve = sum(
            resultado["tempo_solve_segundos"]
            for resultado in resultados
        ) / total
    else:
        menor_tensao = 0.0
        maior_tensao = 0.0
        maior_perda = 0.0
        tempo_medio_preparacao = 0.0
        tempo_medio_solve = 0.0

    simulacoes_por_segundo = (
        total / tempo_total_segundos
        if tempo_total_segundos > 0
        else 0.0
    )

    print("\n" + "=" * 80)
    print("SIMULAÇÕES FINALIZADAS")
    print("=" * 80)
    print(f"Total de simulações executadas: {total}")
    print(f"Convergentes: {total_convergente}")
    print(f"Não convergentes: {total_nao_convergente}")
    print(f"Menor tensão encontrada: {menor_tensao:.6f} pu")
    print(f"Maior tensão encontrada: {maior_tensao:.6f} pu")
    print(f"Maior perda encontrada: {maior_perda:.6f} kW")
    print(f"Tempo médio preparação: {tempo_medio_preparacao:.6f} s")
    print(f"Tempo médio solve: {tempo_medio_solve:.6f} s")
    print(f"Tempo total: {tempo_total_segundos:.2f} segundos")
    print(f"Simulações por segundo: {simulacoes_por_segundo:.4f}")
    print(f"Arquivo resumo final: {arquivo_resumo}")
    print(f"Arquivo checkpoint: {arquivo_checkpoint}")
    print("=" * 80)


def executar_simulacoes_odss(
    arquivo_dss: Path,
    quantidade_cargas_ev: int,
    quantidade_simulacoes: int = 6000,
) -> list[dict]:
    arquivo_dss = Path(arquivo_dss).resolve()

    if not arquivo_dss.exists():
        raise FileNotFoundError(
            f"Arquivo Master do OpenDSS não encontrado:\n{arquivo_dss}"
        )

    if quantidade_cargas_ev <= 0:
        raise ValueError(
            "A quantidade de cargas EV precisa ser maior que zero."
        )

    if quantidade_simulacoes <= 0:
        raise ValueError(
            "A quantidade de simulações precisa ser maior que zero."
        )

    diretorio_resultados = criar_diretorio_resultados(
        arquivo_dss=arquivo_dss,
    )

    arquivo_checkpoint = (
        diretorio_resultados
        / "Checkpoint_Simulacoes_OpenDSSDirect.csv"
    )

    imprimir_cabecalho(
        arquivo_dss=arquivo_dss,
        quantidade_cargas_ev=quantidade_cargas_ev,
        quantidade_simulacoes=quantidade_simulacoes,
        diretorio_resultados=diretorio_resultados,
    )

    tempo_inicio_total = time.perf_counter()

    compilar_circuito_base(
        arquivo_dss=arquivo_dss,
    )

    resultados = []

    for numero_simulacao in range(
        1,
        quantidade_simulacoes + 1,
    ):
        tempo_inicio_preparacao = time.perf_counter()

        arquivo_bus_marker = preparar_cenario(
            numero_simulacao=numero_simulacao,
            quantidade_cargas_ev=quantidade_cargas_ev,
            diretorio_resultados=diretorio_resultados,
        )

        tempo_fim_preparacao = time.perf_counter()

        aplicar_redirect_bus_marker(
            arquivo_bus_marker=arquivo_bus_marker,
        )

        tempo_inicio_solve = time.perf_counter()

        executar_solve()

        tempo_fim_solve = time.perf_counter()

        resultado = coletar_resumo_simulacao(
            numero_simulacao=numero_simulacao,
            arquivo_bus_marker=arquivo_bus_marker,
            tempo_preparacao_segundos=(
                tempo_fim_preparacao
                - tempo_inicio_preparacao
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
            numero_simulacao <= 10
            or numero_simulacao == quantidade_simulacoes
            or numero_simulacao % 100 == 0
        ):
            imprimir_andamento(
                resultado=resultado,
                quantidade_simulacoes=quantidade_simulacoes,
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
        quantidade_cargas_ev=1,
        quantidade_simulacoes=1,
    )

    return resultados[0]