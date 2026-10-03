from pathlib import Path
from datetime import datetime
import csv
import re
import time

try:
    from opendssdirect import dss
except ImportError:
    try:
        import opendssdirect as dss
    except ImportError as exc:
        raise ImportError(
            "O pacote OpenDSSDirect.py não está instalado.\n"
            'Execute: python -m pip install "OpenDSSDirect.py[extras]"'
        ) from exc

from add_ev import executar_add_ev


seed_base_simulacao = 10000
tensao_minima_considerada_pu = 0.4
limite_subtensao_pu = 0.92
limite_sobretensao_pu = 1.05


def criar_diretorio_resultados(arquivo_dss: Path) -> Path:
    data_hora = datetime.now().strftime("%Y%m%d_%H%M%S")
    diretorio_resultados = arquivo_dss.parent / f"simulacoes_odssdirect_{data_hora}"
    diretorio_resultados.mkdir(parents=True, exist_ok=True)
    return diretorio_resultados


def gerar_seed_simulacao(numero_simulacao: int) -> int:
    return seed_base_simulacao + numero_simulacao


def simulacao_com_ev(
    quantidade_ldv: int | None,
    quantidade_two_wheelers: int | None,
    quantidade_trucks: int | None,
) -> bool:
    return (
        quantidade_ldv is not None
        or quantidade_two_wheelers is not None
        or quantidade_trucks is not None
    )


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

        raise RuntimeError(
            f"Erro ao executar comando DSS:\n"
            f"{comando}\n\n"
            f"Detalhe OpenDSS:\n{exc}"
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
    executar_comando_dss("Clear")

def consolidar_arquivos_cargas_ev(
    arquivos_por_alimentador: dict,
    diretorio_resultados: Path,
    numero_simulacao: int,
    seed_simulacao: int,
) -> Path:
    arquivo_consolidado = (
        diretorio_resultados
        / f"Cargas_EV_Sim_{numero_simulacao:05d}_{seed_simulacao}.dss"
    )

    with open(arquivo_consolidado, "w", encoding="utf-8") as saida:
        for alimentador in sorted(arquivos_por_alimentador.keys()):
            linhas = arquivos_por_alimentador[alimentador]

            saida.write(
                f"\n! ========================================\n"
                f"! ALIMENTADOR {alimentador}\n"
                f"! ========================================\n"
            )

            for linha in linhas:
                saida.write(linha + "\n")

    return arquivo_consolidado


def extrair_configuracoes_cargas_arquivo(arquivo_cargas_ev: Path) -> list[dict]:
    configuracoes = []
    nomes_vistos = set()
    padrao_nome = re.compile(r'^\s*New\s+"?(Load\.[^"\s]+)"?', flags=re.IGNORECASE)
    padrao_kw = re.compile(r'(?:^|\s)kw=([+-]?[0-9]+(?:\.[0-9]+)?)', flags=re.IGNORECASE)
    padrao_kw_ativo = re.compile(r'(?:^|\s)kw_ativo=([+-]?[0-9]+(?:\.[0-9]+)?)', flags=re.IGNORECASE)

    with open(arquivo_cargas_ev, "r", encoding="utf-8", errors="ignore") as arquivo:
        for linha in arquivo:
            match_nome = padrao_nome.search(linha)

            if not match_nome:
                continue

            nome = match_nome.group(1)
            chave = nome.lower()

            if chave in nomes_vistos:
                continue

            match_kw_ativo = padrao_kw_ativo.search(linha)
            match_kw = padrao_kw.search(linha)

            if match_kw_ativo:
                kw_ativo = float(match_kw_ativo.group(1))
            elif match_kw:
                kw_ativo = float(match_kw.group(1))
            else:
                raise ValueError(
                    f"Potência kW não encontrada para a carga {nome} em:\n"
                    f"{arquivo_cargas_ev}"
                )

            nomes_vistos.add(chave)
            configuracoes.append(
                {
                    "nome": nome,
                    "kw_ativo": kw_ativo,
                }
            )

    return configuracoes

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
        seed_simulacao = gerar_seed_simulacao(numero_simulacao=numero_simulacao,)

    tempo_inicio = time.perf_counter()

    resultado_sorteio = executar_add_ev(
        quantidade_ldv=quantidade_ldv,
        quantidade_two_wheelers=quantidade_two_wheelers,
        quantidade_trucks=quantidade_trucks,
        diretorio_dss_base=diretorio_dss_base,
        diretorio_bdgd=diretorio_bdgd,
        diretorio_saida=diretorio_resultados,
        numero_simulacao=numero_simulacao,
        seed=seed_simulacao,
    )

    arquivos_por_alimentador = resultado_sorteio["arquivos_por_alimentador"]

    arquivo_cargas_ev = consolidar_arquivos_cargas_ev(
        arquivos_por_alimentador=arquivos_por_alimentador,
        diretorio_resultados=diretorio_resultados,
        numero_simulacao=numero_simulacao,
        seed_simulacao=seed_simulacao,
    )

    alimentadores_sorteados = sorted(arquivos_por_alimentador.keys())
    tempo_preparacao = time.perf_counter() - tempo_inicio

    return {
        "numero_simulacao": numero_simulacao,
        "seed_simulacao": seed_simulacao,
        "quantidade_ldv": quantidade_ldv,
        "quantidade_two_wheelers": quantidade_two_wheelers,
        "quantidade_trucks": quantidade_trucks,
        "arquivo_cargas_ev": arquivo_cargas_ev,
        "nomes_cargas": resultado_sorteio["nomes_cargas"],
        "configuracoes_cargas": resultado_sorteio["configuracoes_cargas"],
        "alimentadores_sorteados": alimentadores_sorteados,
        "total_alimentadores_sorteados": len(alimentadores_sorteados),
        "total_pool_valido": resultado_sorteio["total_pool_valido"],
        "total_pool_invalido": resultado_sorteio["total_pool_invalido"],
        "tempo_preparacao_segundos": tempo_preparacao,
        "modo_simulacao": "COM_EV",
    }


def preparar_cenario_com_ev(
    numero_simulacao: int,
    quantidade_ldv: int,
    quantidade_two_wheelers: int,
    quantidade_trucks: int,
    diretorio_dss_base: Path,
    diretorio_bdgd: Path,
    diretorio_resultados: Path,
) -> dict:
    return gerar_cargas_ev_cenario(
        quantidade_ldv=quantidade_ldv,
        quantidade_two_wheelers=quantidade_two_wheelers,
        quantidade_trucks=quantidade_trucks,
        diretorio_dss_base=diretorio_dss_base,
        diretorio_bdgd=diretorio_bdgd,
        diretorio_resultados=diretorio_resultados,
        numero_simulacao=numero_simulacao,
        seed_simulacao=gerar_seed_simulacao(numero_simulacao=numero_simulacao,),
    )


def preparar_cenario_com_arquivo_ev(
    arquivo_cargas_ev: Path,
    quantidade_ldv: int | None,
    quantidade_two_wheelers: int | None,
    quantidade_trucks: int | None,
) -> dict:
    arquivo_cargas_ev = Path(arquivo_cargas_ev)

    configuracoes_cargas = extrair_configuracoes_cargas_arquivo(
        arquivo_cargas_ev=arquivo_cargas_ev,
    )

    return {
        "numero_simulacao": 1,
        "seed_simulacao": 0,
        "quantidade_ldv": quantidade_ldv or 0,
        "quantidade_two_wheelers": quantidade_two_wheelers or 0,
        "quantidade_trucks": quantidade_trucks or 0,
        "arquivo_cargas_ev": arquivo_cargas_ev,
        "configuracoes_cargas": configuracoes_cargas,
        "nomes_cargas": [item["nome"] for item in configuracoes_cargas],
        "alimentadores_sorteados": [],
        "total_alimentadores_sorteados": 0,
        "total_pool_valido": 0,
        "total_pool_invalido": 0,
        "tempo_preparacao_segundos": 0.0,
        "modo_simulacao": "COM_EV_ARQUIVO",
    }


def preparar_cenario_sem_ev(numero_simulacao: int) -> dict:
    return {
        "numero_simulacao": numero_simulacao,
        "seed_simulacao": gerar_seed_simulacao(numero_simulacao=numero_simulacao,),
        "quantidade_ldv": 0,
        "quantidade_two_wheelers": 0,
        "quantidade_trucks": 0,
        "arquivo_cargas_ev": None,
        "nomes_cargas": [],
        "configuracoes_cargas": [],
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
    quantidade_trucks: int | None,
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
                quantidade_trucks=quantidade_trucks,
            )
        ]

    usar_ev = simulacao_com_ev(
        quantidade_ldv=quantidade_ldv,
        quantidade_two_wheelers=quantidade_two_wheelers,
        quantidade_trucks=quantidade_trucks,
    )

    if not usar_ev:
        return [preparar_cenario_sem_ev(numero_simulacao=1,)]

    if diretorio_dss_base is None:
        raise ValueError(
            "diretorio_dss_base é obrigatório quando houver simulação com EV."
        )

    if diretorio_bdgd is None:
        raise ValueError(
            "diretorio_bdgd é obrigatório quando houver simulação com EV."
        )

    quantidade_ldv = quantidade_ldv or 0
    quantidade_two_wheelers = quantidade_two_wheelers or 0
    quantidade_trucks = quantidade_trucks or 0

    cenarios = []

    for numero_simulacao in range(1, quantidade_simulacoes + 1):
        cenarios.append(
            preparar_cenario_com_ev(
                numero_simulacao=numero_simulacao,
                quantidade_ldv=quantidade_ldv,
                quantidade_two_wheelers=quantidade_two_wheelers,
                quantidade_trucks=quantidade_trucks,
                diretorio_dss_base=Path(diretorio_dss_base),
                diretorio_bdgd=Path(diretorio_bdgd),
                diretorio_resultados=diretorio_resultados,
            )
        )

    return cenarios


def normalizar_lista_redirects(
    arquivos_extra_redirect: list[Path] | None,
) -> list[Path]:
    if not arquivos_extra_redirect:
        return []

    return [
        Path(arquivo)
        for arquivo in arquivos_extra_redirect
        if arquivo is not None
    ]


def obter_todas_configuracoes_cargas(cenarios: list[dict]) -> list[dict]:
    configuracoes = []
    nomes_vistos = set()

    for cenario in cenarios:
        for configuracao in cenario["configuracoes_cargas"]:
            nome = configuracao["nome"]
            chave = nome.lower()

            if chave in nomes_vistos:
                continue

            nomes_vistos.add(chave)
            configuracoes.append(configuracao)

    return configuracoes


def inicializar_cargas(configuracoes_cargas: list[dict]) -> None:
    for configuracao in configuracoes_cargas:
        executar_comando_dss(
            f"Edit {configuracao['nome']} enabled=yes kW=0"
        )


def editar_potencia_carga(nome_carga: str, kw: float) -> None:
    executar_comando_dss(f"Edit {nome_carga} kW={kw:.12g}")


def zerar_cargas(configuracoes_cargas: list[dict]) -> None:
    for configuracao in configuracoes_cargas:
        editar_potencia_carga(nome_carga=configuracao["nome"], kw=0.0,)


def aplicar_cargas_cenario(configuracoes_cargas: list[dict]) -> None:
    for configuracao in configuracoes_cargas:
        editar_potencia_carga(
            nome_carga=configuracao["nome"],
            kw=float(configuracao["kw_ativo"]),
        )

def compilar_circuito_unico(
    arquivo_master: Path,
    cenarios: list[dict],
    arquivos_extra_redirect: list[Path] | None = None,
) -> None:
    arquivo_master = Path(arquivo_master).resolve()

    if not arquivo_master.exists():
        raise FileNotFoundError(
            f"Master OpenDSS não encontrado:\n"
            f"{arquivo_master}"
        )

    limpar_circuito()
    executar_comando_dss(f'Compile "{arquivo_master.as_posix()}"')

    if int(dss.Circuit.NumBuses()) <= 0:
        raise RuntimeError(
            "O Master foi compilado, mas nenhum circuito foi carregado."
        )

    arquivos_redirect = []

    for cenario in cenarios:
        arquivo_cargas_ev = cenario["arquivo_cargas_ev"]

        if arquivo_cargas_ev is not None:
            arquivos_redirect.append(Path(arquivo_cargas_ev).resolve())

    arquivos_redirect.extend(
        Path(arquivo).resolve()
        for arquivo in normalizar_lista_redirects(arquivos_extra_redirect)
    )

    arquivos_redirect = list(dict.fromkeys(arquivos_redirect))

    for arquivo_redirect in arquivos_redirect:
        if not arquivo_redirect.exists():
            raise FileNotFoundError(
                f"Arquivo DSS para Redirect não encontrado:\n"
                f"{arquivo_redirect}"
            )

        executar_comando_dss(f'Redirect "{arquivo_redirect.as_posix()}"')

    inicializar_cargas(
        configuracoes_cargas=obter_todas_configuracoes_cargas(cenarios=cenarios,),
    )


def configurar_simulacao_temporal(hora_simulacao: float) -> None:
    executar_comando_dss("Set Mode=Daily")
    executar_comando_dss("Set Number=1")
    executar_comando_dss("Set Stepsize=1h")
    executar_comando_dss(f"Set Hour={hora_simulacao}")

def preparar_verbose_opendss(
    diretorio_resultados: Path,
    cenario: dict,
) -> Path:
    diretorio_verbose = (
        diretorio_resultados
        / "verbose_opendss"
        / f"Sim_{cenario['numero_simulacao']:05d}_{cenario['seed_simulacao']}"
    )

    diretorio_verbose.mkdir(parents=True, exist_ok=True)

    try:
        dss.Meters.ResetAll()
    except Exception:
        pass

    executar_comando_dss("Set DemandInterval=False", ignorar_erro=True)
    executar_comando_dss(f'Set DataPath="{diretorio_verbose.resolve().as_posix()}"')
    executar_comando_dss(f"Set NormVminpu={limite_subtensao_pu}")
    executar_comando_dss(f"Set NormVmaxpu={limite_sobretensao_pu}")
    executar_comando_dss("Set OverloadReport=True")
    executar_comando_dss("Set DIVerbose=True")
    executar_comando_dss("Set DemandInterval=True")

    return diretorio_verbose

def finalizar_verbose_opendss() -> None:
    executar_comando_dss("CloseDI", ignorar_erro=True)
    executar_comando_dss("Set DemandInterval=False", ignorar_erro=True)
    executar_comando_dss("Set DIVerbose=False", ignorar_erro=True)

def executar_solve(hora_simulacao: float) -> bool:
    executar_comando_dss(f"Set Hour={hora_simulacao}")
    dss.Solution.Solve()
    return bool(dss.Solution.Converged())


def obter_tensoes_validas(
    limite_minimo_pu: float = tensao_minima_considerada_pu,
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


def coletar_verbose_tensao(hora_simulacao: float) -> dict:
    tensoes = obter_tensoes_validas()

    if not tensoes:
        return {
            "Hour": hora_simulacao,
            "Undervoltages": 0,
            "Min Voltage": 0.0,
            "Overvoltages": 0,
            "Max Voltage": 0.0,
        }

    subtensoes = sum(
        1
        for tensao in tensoes
        if tensao < limite_subtensao_pu
    )

    sobretensoes = sum(
        1
        for tensao in tensoes
        if tensao > limite_sobretensao_pu
    )

    return {
        "Hour": hora_simulacao,
        "Undervoltages": subtensoes,
        "Min Voltage": min(tensoes),
        "Overvoltages": sobretensoes,
        "Max Voltage": max(tensoes),
    }


def salvar_verbose_simulacao(
    registros: list[dict],
    diretorio_resultados: Path,
    cenario: dict,
) -> Path:
    arquivo_verbose = (
        diretorio_resultados
        / (
            f"Verbose_Sim_"
            f"{cenario['numero_simulacao']:05d}_"
            f"{cenario['seed_simulacao']}.csv"
        )
    )

    with open(arquivo_verbose, "w", encoding="utf-8-sig", newline="") as arquivo:
        writer = csv.DictWriter(
            arquivo,
            fieldnames=[
                "Hour",
                "Undervoltages",
                "Min Voltage",
                "Overvoltages",
                "Max Voltage",
            ],
            delimiter=";",
        )

        writer.writeheader()
        writer.writerows(registros)

    return arquivo_verbose


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

    tensoes = obter_tensoes_validas()
    tensao_minima = min(tensoes) if tensoes else 0.0
    tensao_maxima = max(tensoes) if tensoes else 0.0

    try:
        iteracoes = int(dss.Solution.MostIterationsDone())
    except Exception:
        iteracoes = 0

    alimentadores_selecionados = ",".join(cenario["alimentadores_sorteados"])
    arquivo_cargas_ev = cenario["arquivo_cargas_ev"]

    diretorio_cargas_ev = (
        str(Path(arquivo_cargas_ev).parent)
        if arquivo_cargas_ev is not None
        else ""
    )

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
        "trucks": cenario["quantidade_trucks"],
        "total_ev": (
            cenario["quantidade_ldv"]
            + cenario["quantidade_two_wheelers"]
            + cenario["quantidade_trucks"]
        ),
        "alimentadores": alimentadores_selecionados,
        "total_alimentadores": cenario["total_alimentadores_sorteados"],
        "circuito": obter_nome_circuito(),
        "convergiu": bool(dss.Solution.Converged()),
        "quantidade_barras": int(dss.Circuit.NumBuses()),
        "quantidade_nos": obter_quantidade_nos(),
        "tensao_minima_pu": tensao_minima,
        "tensao_maxima_pu": tensao_maxima,
        "potencia_total_kw": potencia_total_kw,
        "potencia_total_kvar": potencia_total_kvar,
        "potencia_total_mw": potencia_total_kw / 1000,
        "potencia_total_mvar": potencia_total_kvar / 1000,
        "perdas_kw": perdas_kw,
        "perdas_kvar": perdas_kvar,
        "perdas_mw": perdas_kw / 1000,
        "perdas_mvar": perdas_kvar / 1000,
        "perdas_percentual": (
            perdas_kw / potencia_total_kw * 100
            if potencia_total_kw > 0
            else 0.0
        ),
        "iteracoes": iteracoes,
        "tempo_preparacao_segundos": cenario["tempo_preparacao_segundos"],
        "tempo_compilacao_segundos": tempo_compilacao_segundos,
        "tempo_solve_segundos": tempo_solve_segundos,
        "diretorio_cargas_ev": diretorio_cargas_ev,
        "arquivos_extra_redirect": (
            ",".join(str(Path(arquivo)) for arquivo in arquivos_extra_redirect)
            if arquivos_extra_redirect
            else ""
        ),
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
        "trucks",
        "total_ev",
        "alimentadores",
        "total_alimentadores",
        "circuito",
        "convergiu",
        #"quantidade_barras",
        #"quantidade_nos",
        "tensao_minima_pu",
        "tensao_maxima_pu",
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
        "tempo_preparacao_segundos",
        "tempo_compilacao_segundos",
        "tempo_solve_segundos",
        "diretorio_cargas_ev",
        #"arquivos_extra_redirect",
    ]


def salvar_checkpoint_resultado(
    resultado: dict,
    arquivo_checkpoint: Path,
) -> None:
    arquivo_existe = arquivo_checkpoint.exists()
    colunas = colunas_resultado()

    with open(arquivo_checkpoint, "a", encoding="utf-8-sig", newline="") as arquivo:
        writer = csv.DictWriter(arquivo, fieldnames=colunas, delimiter=";")

        if not arquivo_existe:
            writer.writeheader()

        writer.writerow({coluna: resultado[coluna] for coluna in colunas})


def salvar_resumo_simulacoes(
    resultados: list[dict],
    diretorio_resultados: Path,
) -> Path:
    arquivo_saida = diretorio_resultados / "Resumo_Simulacoes_OpenDSSDirect.csv"
    colunas = colunas_resultado()

    with open(arquivo_saida, "w", encoding="utf-8-sig", newline="") as arquivo:
        writer = csv.DictWriter(arquivo, fieldnames=colunas, delimiter=";")
        writer.writeheader()

        for resultado in resultados:
            writer.writerow({coluna: resultado[coluna] for coluna in colunas})

    return arquivo_saida


def imprimir_summary_opendss(resultado: dict) -> None:
    alimentadores_selecionados = resultado["alimentadores"] or "SEM EV"

    print("")
    print(
        f'SUMMARY OPENDSS - '
        f'Hora {resultado["hora_simulacao"]:.0f}h - '
        f'Simulação {resultado["simulacao"]:05d}/'
        f'{resultado["total_execucoes"]:05d}'
    )
    print("-" * 80)
    print(f'Hour = {resultado["hora_simulacao"]:.6g}')
    print(f'Max pu. voltage = {resultado["tensao_maxima_pu"]:.6g}')
    print(f'Min pu. voltage = {resultado["tensao_minima_pu"]:.6g}')
    print(f'Total Active Power:   {resultado["potencia_total_mw"]:.6f} MW')
    print(f'Total Reactive Power: {resultado["potencia_total_mvar"]:.6f} Mvar')
    print(
        f'Total Active Losses:   '
        f'{resultado["perdas_mw"]:.6f} MW, '
        f'({resultado["perdas_percentual"]:.3f} %)'
    )
    print(f'Total Reactive Losses: {resultado["perdas_mvar"]:.6f} Mvar')
    print(f"Alimentadores com EV: {alimentadores_selecionados}")
    print("-" * 80)


def imprimir_andamento(resultado: dict) -> None:
    print(
        f'Simulação {resultado["simulacao"]:05d} | '
        f'Hora: {resultado["hora_simulacao"]:.0f}h | '
        f'LDV: {resultado["ldv"]} | '
        f'TW: {resultado["two_wheelers"]} | '
        f'Truck: {resultado["trucks"]} | '
        f'Convergiu: {"SIM" if resultado["convergiu"] else "NÃO"} | '
        f'Tensão min: {resultado["tensao_minima_pu"]:.6f} pu | '
        f'Tensão max: {resultado["tensao_maxima_pu"]:.6f} pu'
    )

    imprimir_summary_opendss(resultado)


def executar_simulacoes_odss(
    arquivo_dss: Path,
    diretorio_dss_base: Path | None = None,
    diretorio_bdgd: Path | None = None,
    arquivo_cargas_ev: Path | None = None,
    arquivos_extra_redirect: list[Path] | None = None,
    quantidade_ldv: int | None = None,
    quantidade_two_wheelers: int | None = None,
    quantidade_trucks: int | None = None,
    quantidade_simulacoes: int = 1,
    horas_simulacao: list[float] | None = None,
) -> list[dict]:
    arquivo_dss = Path(arquivo_dss).resolve()

    if horas_simulacao is None:
        horas_simulacao = [19]

    if len(horas_simulacao) != 1:
        raise ValueError("Informe apenas um horário de simulação.")

    try:
        hora_simulacao = float(horas_simulacao[0])
    except (TypeError, ValueError) as exc:
        raise ValueError("O horário da simulação deve ser numérico.") from exc

    if not 0 <= hora_simulacao < 24:
        raise ValueError("O horário da simulação deve estar entre 0 e 23.")

    if not arquivo_dss.exists():
        raise FileNotFoundError(
            f"Master geral OpenDSS não encontrado:\n"
            f"{arquivo_dss}"
        )

    usar_ev_por_arquivo = arquivo_cargas_ev is not None

    usar_ev_por_sorteio = (
        not usar_ev_por_arquivo
        and simulacao_com_ev(
            quantidade_ldv=quantidade_ldv,
            quantidade_two_wheelers=quantidade_two_wheelers,
            quantidade_trucks=quantidade_trucks,
        )
    )

    if usar_ev_por_sorteio:
        quantidade_ldv = quantidade_ldv or 0
        quantidade_two_wheelers = quantidade_two_wheelers or 0
        quantidade_trucks = quantidade_trucks or 0

        if quantidade_ldv < 0 or quantidade_two_wheelers < 0 or quantidade_trucks < 0:
            raise ValueError("As quantidades não podem ser negativas.")

        if quantidade_ldv + quantidade_two_wheelers + quantidade_trucks <= 0:
            raise ValueError(
                "A quantidade total de veículos deve ser maior que zero."
            )

        if diretorio_dss_base is None:
            raise ValueError(
                "diretorio_dss_base é obrigatório para simulação com EV."
            )

        if diretorio_bdgd is None:
            raise ValueError(
                "diretorio_bdgd é obrigatório para simulação com EV."
            )

        diretorio_dss_base = Path(diretorio_dss_base)
        diretorio_bdgd = Path(diretorio_bdgd)

    if usar_ev_por_arquivo:
        arquivo_cargas_ev = Path(arquivo_cargas_ev)

        if not arquivo_cargas_ev.exists():
            raise FileNotFoundError(
                f"Arquivo Cargas_EV informado não encontrado:\n"
                f"{arquivo_cargas_ev}"
            )

        quantidade_simulacoes = 1

    if not usar_ev_por_arquivo and not usar_ev_por_sorteio:
        quantidade_ldv = None
        quantidade_two_wheelers = None
        quantidade_trucks = None
        quantidade_simulacoes = 1

    if quantidade_simulacoes <= 0:
        raise ValueError(
            "A quantidade de simulações deve ser maior que zero."
        )

    diretorio_resultados = criar_diretorio_resultados(arquivo_dss)
    arquivo_checkpoint = diretorio_resultados / "Checkpoint_Simulacoes_OpenDSSDirect.csv"

    tempo_inicio_total = time.perf_counter()

    cenarios = preparar_cenarios(
        quantidade_simulacoes=quantidade_simulacoes,
        quantidade_ldv=quantidade_ldv,
        quantidade_two_wheelers=quantidade_two_wheelers,
        quantidade_trucks=quantidade_trucks,
        diretorio_dss_base=diretorio_dss_base,
        diretorio_bdgd=diretorio_bdgd,
        diretorio_resultados=diretorio_resultados,
        arquivo_cargas_ev=arquivo_cargas_ev,
    )

    tempo_inicio_compilacao = time.perf_counter()

    compilar_circuito_unico(
        arquivo_master=arquivo_dss,
        cenarios=cenarios,
        arquivos_extra_redirect=arquivos_extra_redirect,
    )

    configurar_simulacao_temporal(hora_simulacao=hora_simulacao,)
    tempo_compilacao_unica = time.perf_counter() - tempo_inicio_compilacao

    total_execucoes = len(cenarios)
    resultados = []

    configuracoes_todas = obter_todas_configuracoes_cargas(cenarios=cenarios,)

    for indice_cenario, cenario in enumerate(cenarios, start=1):
        zerar_cargas(configuracoes_cargas=configuracoes_todas,)
        executar_solve(hora_simulacao=hora_simulacao,)

        configuracoes_cenario = cenario["configuracoes_cargas"]
        aplicar_cargas_cenario(configuracoes_cargas=configuracoes_cenario,)

        try:
            diretorio_verbose = preparar_verbose_opendss(
                diretorio_resultados=diretorio_resultados,
                cenario=cenario,
            )

            tempo_inicio_solve = time.perf_counter()

            try:
                executar_solve(hora_simulacao=hora_simulacao,)
            finally:
                finalizar_verbose_opendss()

            tempo_solve = time.perf_counter() - tempo_inicio_solve

            registro_verbose = coletar_verbose_tensao(hora_simulacao=hora_simulacao,)

            resultado = coletar_resumo_simulacao(
                simulacao_global=indice_cenario,
                total_execucoes=total_execucoes,
                cenario=cenario,
                quantidade_simulacoes=len(cenarios),
                hora_simulacao=hora_simulacao,
                tempo_compilacao_segundos=tempo_compilacao_unica,
                tempo_solve_segundos=tempo_solve,
                arquivos_extra_redirect=arquivos_extra_redirect,
            )

            resultados.append(resultado)

            salvar_checkpoint_resultado(
                resultado=resultado,
                arquivo_checkpoint=arquivo_checkpoint,
            )

            arquivo_verbose = salvar_verbose_simulacao(
                registros=[registro_verbose],
                diretorio_resultados=diretorio_resultados,
                cenario=cenario,
            )

            imprimir_andamento(resultado=resultado,)
            print(f"Verbose resumido: {arquivo_verbose}")
            print(f"Verbose OpenDSS: {diretorio_verbose}")

        finally:
            zerar_cargas(configuracoes_cargas=configuracoes_cenario,)

    arquivo_resumo = salvar_resumo_simulacoes(
        resultados=resultados,
        diretorio_resultados=diretorio_resultados,
    )

    tempo_total = time.perf_counter() - tempo_inicio_total

    print("")
    print("=" * 80)
    print("SIMULAÇÕES FINALIZADAS")
    print("=" * 80)
    print(f"Horário simulado: {hora_simulacao:g}h")
    print(f"Total de cenários: {len(cenarios)}")
    print(f"Compilação única: {tempo_compilacao_unica:.2f} segundos")
    print(f"Tempo total: {tempo_total:.2f} segundos")
    print(f"Resumo: {arquivo_resumo}")
    print(f"Checkpoint: {arquivo_checkpoint}")
    print("=" * 80)

    return resultados
