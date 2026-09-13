from pathlib import Path
from datetime import datetime
import csv
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


SEED_BASE_SIMULACAO = 10000
TENSAO_MINIMA_CONSIDERADA_PU = 0.4


def criar_diretorio_resultados(arquivo_dss: Path) -> Path:
    data_hora = datetime.now().strftime("%Y%m%d_%H%M%S")
    diretorio_resultados = arquivo_dss.parent / f"simulacoes_odssdirect_{data_hora}"
    diretorio_resultados.mkdir(parents=True, exist_ok=True)
    return diretorio_resultados


def gerar_seed_simulacao(numero_simulacao: int) -> int:
    return SEED_BASE_SIMULACAO + numero_simulacao


def simulacao_com_ev(quantidade_ldv: int | None, quantidade_two_wheelers: int | None) -> bool:
    return quantidade_ldv is not None or quantidade_two_wheelers is not None


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


def executar_comando_dss(comando: str, ignorar_erro: bool = False) -> str:
    try:
        resultado = dss.Text.Command(comando)
    except Exception as exc:
        if ignorar_erro:
            return ""
        raise RuntimeError(f"Erro ao executar comando DSS:\n{comando}") from exc
    mensagem_erro = obter_ultimo_erro_dss()
    if mensagem_erro and not ignorar_erro:
        raise RuntimeError(f"Erro retornado pelo DSS ao executar:\n{comando}\n\n{mensagem_erro}")
    if resultado is None:
        return ""
    return str(resultado).strip()


def limpar_circuito() -> None:
    executar_comando_dss("Clear")


def consolidar_arquivos_cargas_ev(
    arquivos_por_alimentador: dict,
    diretorio_resultados: Path,
    numero_simulacao: int,
    seed_simulacao: int,
) -> Path:
    arquivo_consolidado = diretorio_resultados / f"Cargas_EV_Sim_{numero_simulacao:05d}_{seed_simulacao}.dss"
    with open(arquivo_consolidado, "w", encoding="utf-8") as saida:
        for alimentador in sorted(arquivos_por_alimentador.keys()):
            arquivo_origem = Path(arquivos_por_alimentador[alimentador])
            if not arquivo_origem.exists():
                raise FileNotFoundError(f"Arquivo EV não encontrado para {alimentador}:\n{arquivo_origem}")
            saida.write(f'\n! ========================================\n! ALIMENTADOR {alimentador}\n! ========================================\n')
            with open(arquivo_origem, "r", encoding="utf-8") as origem:
                conteudo = origem.read()
                saida.write(conteudo)
                if conteudo and not conteudo.endswith("\n"):
                    saida.write("\n")
    return arquivo_consolidado


def gerar_cargas_ev_cenario(
    quantidade_ldv: int,
    quantidade_two_wheelers: int,
    diretorio_dss_base: Path,
    diretorio_bdgd: Path,
    diretorio_resultados: Path,
    numero_simulacao: int = 1,
    seed_simulacao: int | None = None,
    quantidade_trucks: int = 0,
) -> dict:
    if seed_simulacao is None:
        seed_simulacao = gerar_seed_simulacao(numero_simulacao=numero_simulacao)
    tempo_inicio = time.perf_counter()
    resultado_sorteio = executar_add_ev(
        quantidade_ldv=quantidade_ldv,
        quantidade_two_wheelers=quantidade_two_wheelers,
        diretorio_dss_base=diretorio_dss_base,
        diretorio_bdgd=diretorio_bdgd,
        diretorio_saida=diretorio_resultados,
        numero_simulacao=numero_simulacao,
        seed=seed_simulacao,
        quantidade_trucks=quantidade_trucks,
    )
    arquivos_por_alimentador = resultado_sorteio["arquivos_por_alimentador"]
    arquivo_cargas_ev = consolidar_arquivos_cargas_ev(
        arquivos_por_alimentador=arquivos_por_alimentador,
        diretorio_resultados=diretorio_resultados,
        numero_simulacao=numero_simulacao,
        seed_simulacao=seed_simulacao,
    )
    tempo_fim = time.perf_counter()
    alimentadores_sorteados = sorted(arquivos_por_alimentador.keys())
    return {
        "numero_simulacao": numero_simulacao,
        "seed_simulacao": seed_simulacao,
        "quantidade_ldv": quantidade_ldv,
        "quantidade_two_wheelers": quantidade_two_wheelers,
        "quantidade_trucks": quantidade_trucks,
        "arquivo_cargas_ev": arquivo_cargas_ev,
        "alimentadores_sorteados": alimentadores_sorteados,
        "total_alimentadores_sorteados": len(alimentadores_sorteados),
        "total_pool_valido": resultado_sorteio["total_pool_valido"],
        "total_pool_invalido": resultado_sorteio["total_pool_invalido"],
        "tempo_preparacao_segundos": tempo_fim - tempo_inicio,
        "modo_simulacao": "COM_EV",
    }


def preparar_cenario_com_ev(
    numero_simulacao: int,
    quantidade_ldv: int,
    quantidade_two_wheelers: int,
    diretorio_dss_base: Path,
    diretorio_bdgd: Path,
    diretorio_resultados: Path,
) -> dict:
    return gerar_cargas_ev_cenario(
        quantidade_ldv=quantidade_ldv,
        quantidade_two_wheelers=quantidade_two_wheelers,
        diretorio_dss_base=diretorio_dss_base,
        diretorio_bdgd=diretorio_bdgd,
        diretorio_resultados=diretorio_resultados,
        numero_simulacao=numero_simulacao,
        seed_simulacao=gerar_seed_simulacao(numero_simulacao=numero_simulacao),
    )


def preparar_cenario_com_arquivo_ev(
    arquivo_cargas_ev: Path,
    quantidade_ldv: int | None,
    quantidade_two_wheelers: int | None,
) -> dict:
    return {
        "numero_simulacao": 1,
        "seed_simulacao": 0,
        "quantidade_ldv": quantidade_ldv or 0,
        "quantidade_two_wheelers": quantidade_two_wheelers or 0,
        "arquivo_cargas_ev": Path(arquivo_cargas_ev),
        "alimentadores_sorteados": [],
        "total_alimentadores_sorteados": 0,
        "total_pool_valido": 0,
        "total_pool_invalido": 0,
        "tempo_preparacao_segundos": 0.0,
        "modo_simulacao": "COM_EV_ARQUIVO",
    }


def preparar_cenario_sem_ev(numero_simulacao: int) -> dict:
    seed_simulacao = gerar_seed_simulacao(numero_simulacao=numero_simulacao)
    return {
        "numero_simulacao": numero_simulacao,
        "seed_simulacao": seed_simulacao,
        "quantidade_ldv": 0,
        "quantidade_two_wheelers": 0,
        "arquivo_cargas_ev": None,
        "alimentadores_sorteados": [],
        "total_alimentadores_sorteados": 0,
        "total_pool_valido": 0,
        "total_pool_invalido": 0,
        "tempo_preparacao_segundos": 0.0,
        "modo_simulacao": "SEM_EV",
    }


def preparar_cenarios(
    quantidade_simulacoes: int,
    quantidade_ldv: int | None,
    quantidade_two_wheelers: int | None,
    diretorio_dss_base: Path | None,
    diretorio_bdgd: Path | None,
    diretorio_resultados: Path,
    arquivo_cargas_ev: Path | None = None,
) -> list[dict]:
    if arquivo_cargas_ev is not None:
        return [
            preparar_cenario_com_arquivo_ev(
                arquivo_cargas_ev=arquivo_cargas_ev,
                quantidade_ldv=quantidade_ldv,
                quantidade_two_wheelers=quantidade_two_wheelers,
            )
        ]
    usar_ev = simulacao_com_ev(
        quantidade_ldv=quantidade_ldv,
        quantidade_two_wheelers=quantidade_two_wheelers,
    )
    if not usar_ev:
        return [preparar_cenario_sem_ev(numero_simulacao=1)]
    if diretorio_dss_base is None:
        raise ValueError("diretorio_dss_base é obrigatório quando houver simulação com EV.")
    if diretorio_bdgd is None:
        raise ValueError("diretorio_bdgd é obrigatório quando houver simulação com EV.")
    quantidade_ldv = quantidade_ldv or 0
    quantidade_two_wheelers = quantidade_two_wheelers or 0
    cenarios = []
    for numero_simulacao in range(1, quantidade_simulacoes + 1):
        cenarios.append(
            preparar_cenario_com_ev(
                numero_simulacao=numero_simulacao,
                quantidade_ldv=quantidade_ldv,
                quantidade_two_wheelers=quantidade_two_wheelers,
                diretorio_dss_base=Path(diretorio_dss_base),
                diretorio_bdgd=Path(diretorio_bdgd),
                diretorio_resultados=diretorio_resultados,
            )
        )
    return cenarios


def normalizar_lista_redirects(arquivos_extra_redirect: list[Path] | None) -> list[Path]:
    if not arquivos_extra_redirect:
        return []
    arquivos = []
    for arquivo in arquivos_extra_redirect:
        if arquivo is None:
            continue
        arquivos.append(Path(arquivo))
    return arquivos


def compilar_circuito_simulacao(
    arquivo_master: Path,
    arquivo_cargas_ev: Path | None = None,
    arquivos_extra_redirect: list[Path] | None = None,
) -> None:
    arquivo_master = Path(arquivo_master).resolve()
    if not arquivo_master.exists():
        raise FileNotFoundError(f"Master OpenDSS não encontrado:\n{arquivo_master}")
    limpar_circuito()
    executar_comando_dss(f'Compile "{arquivo_master}"')
    quantidade_barras = int(dss.Circuit.NumBuses())
    if quantidade_barras <= 0:
        raise RuntimeError("O Master foi compilado, mas nenhum circuito foi carregado.")
    arquivos_redirect = []
    if arquivo_cargas_ev is not None:
        arquivos_redirect.append(Path(arquivo_cargas_ev))
    arquivos_redirect.extend(normalizar_lista_redirects(arquivos_extra_redirect))
    for arquivo_redirect in arquivos_redirect:
        arquivo_redirect = Path(arquivo_redirect).resolve()
        if not arquivo_redirect.exists():
            raise FileNotFoundError(f"Arquivo DSS para Redirect não encontrado:\n{arquivo_redirect}")
        executar_comando_dss(f'Redirect "{arquivo_redirect}"')


def executar_solve(hora_simulacao: float) -> bool:
    executar_comando_dss("Set Mode=Daily")
    executar_comando_dss("Set Number=1")
    executar_comando_dss("Set Stepsize=1h")
    executar_comando_dss(f"Set Hour={hora_simulacao}")
    dss.Solution.Solve()
    return bool(dss.Solution.Converged())


def obter_tensoes_validas(limite_minimo_pu: float = TENSAO_MINIMA_CONSIDERADA_PU) -> list[float]:
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
    cenario: dict,
    quantidade_simulacoes: int,
    hora_simulacao: float,
    tempo_compilacao_segundos: float,
    tempo_solve_segundos: float,
    arquivos_extra_redirect: list[Path] | None = None,
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
    perdas_percentual = perdas_kw / potencia_total_kw * 100 if potencia_total_kw > 0 else 0.0
    tensoes_validas = obter_tensoes_validas()
    tensao_minima = min(tensoes_validas) if tensoes_validas else 0.0
    tensao_maxima = max(tensoes_validas) if tensoes_validas else 0.0
    try:
        iteracoes = int(dss.Solution.MostIterationsDone())
    except Exception:
        iteracoes = 0
    arquivos_extra_texto = ",".join(str(Path(arquivo)) for arquivo in arquivos_extra_redirect) if arquivos_extra_redirect else ""
    return {
        "simulacao": simulacao_global,
        "total_execucoes": total_execucoes,
        "cenario": cenario["numero_simulacao"],
        "seed_simulacao": cenario["seed_simulacao"],
        "modo_simulacao": cenario["modo_simulacao"],
        "simulacoes_por_horario": quantidade_simulacoes,
        "hora_simulacao": hora_simulacao,
        "ldv": cenario["quantidade_ldv"],
        "two_wheelers": cenario["quantidade_two_wheelers"],
        "total_ev": cenario["quantidade_ldv"] + cenario["quantidade_two_wheelers"],
        "alimentadores": ",".join(cenario["alimentadores_sorteados"]),
        "total_alimentadores": cenario["total_alimentadores_sorteados"],
        "circuito": obter_nome_circuito(),
        "convergiu": bool(dss.Solution.Converged()),
        "quantidade_barras": int(dss.Circuit.NumBuses()),
        "quantidade_nos": obter_quantidade_nos(),
        "tensao_maxima_pu": tensao_maxima,
        "tensao_minima_pu": tensao_minima,
        "potencia_total_kw": potencia_total_kw,
        "potencia_total_kvar": potencia_total_kvar,
        "potencia_total_mw": potencia_total_mw,
        "potencia_total_mvar": potencia_total_mvar,
        "perdas_kw": perdas_kw,
        "perdas_kvar": perdas_kvar,
        "perdas_mw": perdas_mw,
        "perdas_mvar": perdas_mvar,
        "perdas_percentual": perdas_percentual,
        "iteracoes": iteracoes,
        "tempo_preparacao_segundos": cenario["tempo_preparacao_segundos"],
        "tempo_compilacao_segundos": tempo_compilacao_segundos,
        "tempo_solve_segundos": tempo_solve_segundos,
        "diretorio_cargas_ev": str(cenario["arquivo_cargas_ev"]) if cenario["arquivo_cargas_ev"] is not None else "",
        "arquivos_extra_redirect": arquivos_extra_texto,
    }


def colunas_resultado() -> list[str]:
    return [
        "simulacao",
        #"total_execucoes",
        #"cenario",
        #"seed_simulacao",
        #"modo_simulacao",
        #"simulacoes_por_horario",
        "hora_simulacao",
        "ldv",
        "two_wheelers",
        "total_ev",
        "alimentadores",
        "total_alimentadores",
        "circuito",
        "convergiu",
        #"quantidade_barras",
        #"quantidade_nos",
        "tensao_maxima_pu",
        "tensao_minima_pu",
        "potencia_total_kw",
        "potencia_total_kvar",
        "potencia_total_mw",
        "potencia_total_mvar",
        "perdas_kw",
        "perdas_kvar",
        "perdas_mw",
        "perdas_mvar",
        "perdas_percentual",
        #"iteracoes",
        #"tempo_preparacao_segundos",
        #"tempo_compilacao_segundos",
        #"tempo_solve_segundos",
        "diretorio_cargas_ev",
        #"arquivos_extra_redirect",
    ]


def salvar_checkpoint_resultado(resultado: dict, arquivo_checkpoint: Path) -> None:
    arquivo_existe = arquivo_checkpoint.exists()
    colunas = colunas_resultado()
    with open(arquivo_checkpoint, "a", encoding="utf-8-sig", newline="") as arquivo:
        writer = csv.DictWriter(arquivo, fieldnames=colunas, delimiter=";")
        if not arquivo_existe:
            writer.writeheader()
        writer.writerow({coluna: resultado[coluna] for coluna in colunas})


def salvar_resumo_simulacoes(resultados: list[dict], diretorio_resultados: Path) -> Path:
    arquivo_saida = diretorio_resultados / "Resumo_Simulacoes_OpenDSSDirect.csv"
    colunas = colunas_resultado()
    with open(arquivo_saida, "w", encoding="utf-8-sig", newline="") as arquivo:
        writer = csv.DictWriter(arquivo, fieldnames=colunas, delimiter=";")
        writer.writeheader()
        for resultado in resultados:
            writer.writerow({coluna: resultado[coluna] for coluna in colunas})
    return arquivo_saida


def imprimir_summary_opendss(resultado: dict) -> None:
    alimentadores = resultado["alimentadores"] or "SEM EV"
    print("")
    print(
        f'SUMMARY OPENDSS - Hora {resultado["hora_simulacao"]:.0f}h - '
        f'Cenário {resultado["cenario"]:05d}/{resultado["simulacoes_por_horario"]:05d} - '
        f'Seed {resultado["seed_simulacao"]} - '
        f'Execução {resultado["simulacao"]:05d}/{resultado["total_execucoes"]:05d}'
    )
    print("-" * 80)
    print(f'Modo = {resultado["modo_simulacao"]}')
    print(f'Hour = {resultado["hora_simulacao"]:.6g}')
    print(f'Max pu. voltage = {resultado["tensao_maxima_pu"]:.6g}')
    print(f'Min pu. voltage = {resultado["tensao_minima_pu"]:.6g}')
    print("Total Active Power:   " f'{resultado["potencia_total_mw"]:.6f} MW')
    print("Total Reactive Power: " f'{resultado["potencia_total_mvar"]:.6f} Mvar')
    print(
        "Total Active Losses:   "
        f'{resultado["perdas_mw"]:.6f} MW, '
        f'({resultado["perdas_percentual"]:.3f} %)'
    )
    print("Total Reactive Losses: " f'{resultado["perdas_mvar"]:.6f} Mvar')
    print(f"Alimentadores com EV: {alimentadores}")
    print("-" * 80)


def imprimir_andamento(resultado: dict) -> None:
    print(
        f'Cenário {resultado["cenario"]:05d} | '
        f'Seed: {resultado["seed_simulacao"]} | '
        f'Modo: {resultado["modo_simulacao"]} | '
        f'Hora: {resultado["hora_simulacao"]:.0f}h | '
        f'LDV: {resultado["ldv"]} | '
        f'TW: {resultado["two_wheelers"]} | '
        f'Convergiu: {"SIM" if resultado["convergiu"] else "NÃO"} | '
        f'Tensão min: {resultado["tensao_minima_pu"]:.6f} pu | '
        f'Tensão max: {resultado["tensao_maxima_pu"]:.6f} pu'
    )
    imprimir_summary_opendss(resultado)
    print("")
    print("=" * 150, " - fim")
    print("")


def executar_simulacoes_odss(
    arquivo_dss: Path,
    diretorio_dss_base: Path | None = None,
    diretorio_bdgd: Path | None = None,
    arquivo_cargas_ev: Path | None = None,
    arquivos_extra_redirect: list[Path] | None = None,
    quantidade_ldv: int | None = None,
    quantidade_two_wheelers: int | None = None,
    quantidade_simulacoes: int = 1,
    horas_simulacao: list[float] | None = None,
) -> list[dict]:
    arquivo_dss = Path(arquivo_dss).resolve()
    if horas_simulacao is None:
        horas_simulacao = [19, 20, 21, 22]
    if not arquivo_dss.exists():
        raise FileNotFoundError(f"Master geral OpenDSS não encontrado:\n{arquivo_dss}")
    usar_ev_por_arquivo = arquivo_cargas_ev is not None
    usar_ev_por_sorteio = not usar_ev_por_arquivo and simulacao_com_ev(
        quantidade_ldv=quantidade_ldv,
        quantidade_two_wheelers=quantidade_two_wheelers,
    )
    if usar_ev_por_sorteio:

        quantidade_ldv = quantidade_ldv or 0
        quantidade_two_wheelers = quantidade_two_wheelers or 0
        if quantidade_ldv < 0 or quantidade_two_wheelers < 0:
            raise ValueError("As quantidades não podem ser negativas.")

        if quantidade_ldv + quantidade_two_wheelers <= 0:
            raise ValueError("Quando os parâmetros de EV forem informados, a quantidade total deve ser maior que zero.")

        if diretorio_dss_base is None:
            raise ValueError("diretorio_dss_base é obrigatório para simulação com EV.")

        if diretorio_bdgd is None:
            raise ValueError("diretorio_bdgd é obrigatório para simulação com EV.")

        diretorio_dss_base = Path(diretorio_dss_base)
        diretorio_bdgd = Path(diretorio_bdgd)

    if usar_ev_por_arquivo:
        arquivo_cargas_ev = Path(arquivo_cargas_ev)

        if not arquivo_cargas_ev.exists():
            raise FileNotFoundError(f"Arquivo Cargas_EV informado não encontrado:\n{arquivo_cargas_ev}")
        quantidade_simulacoes = 1

    if not usar_ev_por_arquivo and not usar_ev_por_sorteio:
        quantidade_ldv = None
        quantidade_two_wheelers = None
        quantidade_simulacoes = 1

    if quantidade_simulacoes <= 0:
        raise ValueError("A quantidade de cenários deve ser maior que zero.")

    diretorio_resultados = criar_diretorio_resultados(arquivo_dss)
    arquivo_checkpoint = diretorio_resultados / "Checkpoint_Simulacoes_OpenDSSDirect.csv"
    print("=" * 80)
    print("SIMULAÇÃO GLOBAL OPENDSSDIRECT")
    print("=" * 80)
    print(f"Master geral: {arquivo_dss}")
    print(f"Horários: {horas_simulacao}")
    print(f"Diretório resultados: {diretorio_resultados}")
    print("=" * 80)
    tempo_inicio_total = time.perf_counter()
    cenarios = preparar_cenarios(
        quantidade_simulacoes=quantidade_simulacoes,
        quantidade_ldv=quantidade_ldv,
        quantidade_two_wheelers=quantidade_two_wheelers,
        diretorio_dss_base=diretorio_dss_base,
        diretorio_bdgd=diretorio_bdgd,
        diretorio_resultados=diretorio_resultados,
        arquivo_cargas_ev=arquivo_cargas_ev,
    )
    total_execucoes = len(cenarios) * len(horas_simulacao)
    resultados = []
    simulacao_global = 0
    for cenario in cenarios:
        for hora_simulacao in horas_simulacao:
            simulacao_global += 1
            tempo_inicio_compilacao = time.perf_counter()
            compilar_circuito_simulacao(
                arquivo_master=arquivo_dss,
                arquivo_cargas_ev=cenario["arquivo_cargas_ev"],
                arquivos_extra_redirect=arquivos_extra_redirect,
            )
            tempo_fim_compilacao = time.perf_counter()
            tempo_inicio_solve = time.perf_counter()
            executar_solve(hora_simulacao=hora_simulacao)
            tempo_fim_solve = time.perf_counter()
            resultado = coletar_resumo_simulacao(
                simulacao_global=simulacao_global,
                total_execucoes=total_execucoes,
                cenario=cenario,
                quantidade_simulacoes=len(cenarios),
                hora_simulacao=hora_simulacao,
                tempo_compilacao_segundos=tempo_fim_compilacao - tempo_inicio_compilacao,
                tempo_solve_segundos=tempo_fim_solve - tempo_inicio_solve,
                arquivos_extra_redirect=arquivos_extra_redirect,
            )
            resultados.append(resultado)
            salvar_checkpoint_resultado(resultado=resultado, arquivo_checkpoint=arquivo_checkpoint)
            imprimir_andamento(resultado)
    arquivo_resumo = salvar_resumo_simulacoes(resultados=resultados, diretorio_resultados=diretorio_resultados)
    tempo_total = time.perf_counter() - tempo_inicio_total
    print("")
    print("=" * 80)
    print("SIMULAÇÕES FINALIZADAS")
    print("=" * 80)
    print(f"Total de cenários: {len(cenarios)}")
    print(f"Total de execuções: {len(resultados)}")
    print(f"Tempo total: {tempo_total:.2f} segundos")
    print(f"Resumo: {arquivo_resumo}")
    print(f"Checkpoint: {arquivo_checkpoint}")
    print("=" * 80)
    return resultados