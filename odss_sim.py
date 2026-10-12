from pathlib import Path
from datetime import datetime
import csv
import re
import time
import secrets

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

from add_ev import (
    executar_add_ev,
    preparar_pool_ev,
    salvar_cenario_pool_ev,
    sortear_cenario_pool_ev,
)


seeds_usadas = set()
tensao_minima_considerada_pu = 0.4
limite_subtensao_pu = 0.92
limite_sobretensao_pu = 1.05
tamanho_lote_comandos = 500


def criar_diretorio_resultados(arquivo_dss: Path) -> Path:
    data_hora = datetime.now().strftime("%Y%m%d_%H%M%S")
    diretorio_resultados = arquivo_dss.parent / f"simulacoes_odssdirect_{data_hora}"
    diretorio_resultados.mkdir(parents=True, exist_ok=True)
    return diretorio_resultados


def gerar_seed_simulacao(numero_simulacao: int) -> int:
    while True:
        seed = secrets.randbelow(2_000_000_000) + 1

        if seed not in seeds_usadas:
            seeds_usadas.add(seed)
            return seed


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



def executar_comandos_em_lote(comandos: list[str]) -> None:
    if not comandos:
        return

    for inicio in range(0, len(comandos), tamanho_lote_comandos):
        lote = comandos[inicio:inicio + tamanho_lote_comandos]
        bloco = "\n".join(lote)

        try:
            dss(bloco)
        except Exception:
            for comando in lote:
                executar_comando_dss(comando)


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
    comandos = [
        f"Edit {configuracao['nome']} kW=0"
        for configuracao in configuracoes_cargas
    ]
    executar_comandos_em_lote(comandos=comandos,)


def aplicar_cargas_cenario(configuracoes_cargas: list[dict]) -> None:
    comandos = [
        f"Edit {configuracao['nome']} kW={float(configuracao['kw_ativo']):.12g}"
        for configuracao in configuracoes_cargas
    ]
    executar_comandos_em_lote(comandos=comandos,)


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


def compilar_circuito_pool(
    arquivo_master: Path,
    arquivo_pool_ev: Path,
    arquivos_extra_redirect: list[Path] | None = None,
) -> None:
    arquivo_master = Path(arquivo_master).resolve()
    arquivo_pool_ev = Path(arquivo_pool_ev).resolve()

    if not arquivo_master.exists():
        raise FileNotFoundError(
            f"Master OpenDSS não encontrado:\n"
            f"{arquivo_master}"
        )

    if not arquivo_pool_ev.exists():
        raise FileNotFoundError(
            f"Pool de cargas EV não encontrado:\n"
            f"{arquivo_pool_ev}"
        )

    limpar_circuito()
    executar_comando_dss(f'Compile "{arquivo_master.as_posix()}"')

    if int(dss.Circuit.NumBuses()) <= 0:
        raise RuntimeError(
            "O Master foi compilado, mas nenhum circuito foi carregado."
        )

    arquivos_redirect = [arquivo_pool_ev]
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


def configurar_simulacao_temporal(hora_simulacao: float) -> None:
    executar_comando_dss("Set Mode=Daily")
    executar_comando_dss("Set Number=1")
    executar_comando_dss("Set Stepsize=1h")
    executar_comando_dss(f"Set Hour={hora_simulacao}")


def desativar_demand_interval() -> None:
    executar_comando_dss("CloseDI", ignorar_erro=True)
    executar_comando_dss("Set DemandInterval=False", ignorar_erro=True)
    executar_comando_dss("Set DIVerbose=False", ignorar_erro=True)
    executar_comando_dss("Set OverloadReport=False", ignorar_erro=True)


def montar_sufixo_resultado(cenario: dict) -> str:
    return (
        f"{cenario['seed_simulacao']}_"
        f"{int(cenario['quantidade_ldv']):04d}_"
        f"{int(cenario['quantidade_two_wheelers']):04d}_"
        f"{int(cenario['quantidade_trucks']):02d}"
    )


def preparar_diretorio_verbose_opendss(
    diretorio_resultados: Path,
    cenario: dict,
) -> Path:
    diretorio_verbose = diretorio_resultados / "resultados"
    nome_caso = (
        f"Sim_{cenario['numero_simulacao']:05d}_"
        f"{cenario['seed_simulacao']}"
    )
    diretorio_caso = diretorio_verbose / nome_caso
    diretorio_caso.mkdir(parents=True, exist_ok=True)
    return diretorio_caso


def exportar_verbose_opendss(
    diretorio_resultados: Path,
    cenario: dict,
) -> Path:
    diretorio_caso = preparar_diretorio_verbose_opendss(
        diretorio_resultados=diretorio_resultados,
        cenario=cenario,
    )

    sufixo_resultado = montar_sufixo_resultado(cenario=cenario,)

    exportacoes = [
        ("Voltages", f"Voltages_{sufixo_resultado}.csv"),
        ("SeqVoltages", f"SeqVoltages_{sufixo_resultado}.csv"),
        #("Currents", f"Currents_{sufixo_resultado}.csv"),
        #("SeqCurrents", f"SeqCurrents_{sufixo_resultado}.csv"),
        #("Powers", f"Powers_{sufixo_resultado}.csv"),
        #("SeqPowers", f"SeqPowers_{sufixo_resultado}.csv"),
        ("Losses", f"Losses_{sufixo_resultado}.csv"),
        ("Overloads", f"Overloads_{sufixo_resultado}.csv"),
        #("Meters", f"Meters_{sufixo_resultado}.csv"),
        #("Taps", f"Taps_{sufixo_resultado}.csv"),
        ("Summary", f"Summary_{sufixo_resultado}.csv"),
        #("ElemVoltages", f"ElemVoltages_{sufixo_resultado}.csv"),
        #("ElemCurrents", f"ElemCurrents_{sufixo_resultado}.csv"),
        #("ElemPowers", f"ElemPowers_{sufixo_resultado}.csv"),
    ]

    exportacoes_ok = []
    exportacoes_erro = []
    tempos_exportacoes = []
    tempo_inicio_exports = time.perf_counter()

    for tipo_exportacao, nome_arquivo in exportacoes:
        arquivo_saida = diretorio_caso / nome_arquivo
        comando = (
            f'Export {tipo_exportacao} "'
            f'{arquivo_saida.resolve().as_posix()}"'
        )

        print(f"    Export {tipo_exportacao}...", end="", flush=True)
        tempo_inicio_exportacao = time.perf_counter()
        status = "OK"
        erro = ""

        try:
            executar_comando_dss(comando)
            exportacoes_ok.append(nome_arquivo)
        except Exception as exc:
            status = "ERRO"
            erro = str(exc).replace("\n", " ")
            exportacoes_erro.append(f"{tipo_exportacao}: {exc}")

        tempo_exportacao = time.perf_counter() - tempo_inicio_exportacao
        tamanho_bytes = arquivo_saida.stat().st_size if arquivo_saida.exists() else 0
        tamanho_mb = tamanho_bytes / (1024 * 1024)

        tempos_exportacoes.append(
            {
                "exportacao": tipo_exportacao,
                "arquivo": nome_arquivo,
                "status": status,
                "tempo_segundos": tempo_exportacao,
                "tamanho_bytes": tamanho_bytes,
                "tamanho_mb": tamanho_mb,
                "erro": erro,
            }
        )

        print(
            f" {status} | {tempo_exportacao:.2f} s | {tamanho_mb:.2f} MB",
            flush=True,
        )

    tempo_total_exports = time.perf_counter() - tempo_inicio_exports
    # arquivo_tempos = diretorio_caso / f"Tempos_Exports_{sufixo_resultado}.csv"
    #
    # with open(arquivo_tempos, "w", encoding="utf-8-sig", newline="") as arquivo:
    #     writer = csv.DictWriter(
    #         arquivo,
    #         fieldnames=[
    #             "exportacao",
    #             "arquivo",
    #             "status",
    #             "tempo_segundos",
    #             "tamanho_bytes",
    #             "tamanho_mb",
    #             "erro",
    #         ],
    #         delimiter=";",
    #     )
    #     writer.writeheader()
    #     writer.writerows(tempos_exportacoes)

    print(
        f"    Total dos exports: {tempo_total_exports:.2f} segundos",
        flush=True,
    )

    return diretorio_caso

def capturar_taps_transformadores() -> dict[str, list[float]]:
    estados = {}

    for nome in list(dss.Transformers.AllNames() or []):
        dss.Transformers.Name(nome)
        quantidade_enrolamentos = int(dss.Transformers.NumWindings())
        taps = []

        for enrolamento in range(1, quantidade_enrolamentos + 1):
            dss.Transformers.Wdg(enrolamento)
            taps.append(float(dss.Transformers.Tap()))

        estados[nome] = taps

    return estados


def restaurar_taps_transformadores(estados: dict[str, list[float]]) -> None:
    for nome, taps in estados.items():
        dss.Transformers.Name(nome)

        for enrolamento, tap in enumerate(taps, start=1):
            dss.Transformers.Wdg(enrolamento)
            dss.Transformers.Tap(tap)


def capturar_estados_capacitores() -> dict[str, list[int]]:
    estados = {}

    for nome in list(dss.Capacitors.AllNames() or []):
        dss.Capacitors.Name(nome)
        estados[nome] = list(dss.Capacitors.States() or [])

    return estados


def restaurar_estados_capacitores(estados: dict[str, list[int]]) -> None:
    for nome, estados_passos in estados.items():
        dss.Capacitors.Name(nome)
        dss.Capacitors.States(estados_passos)


def resetar_interface_controle(interface) -> None:
    try:
        indice = interface.First()
    except Exception:
        return

    while indice > 0:
        try:
            interface.Reset()
        except Exception:
            pass

        indice = interface.Next()


def resetar_controles() -> None:
    try:
        dss.CtrlQueue.ClearQueue()
    except Exception:
        pass

    resetar_interface_controle(dss.RegControls)
    resetar_interface_controle(dss.CapControls)
    resetar_interface_controle(dss.SwtControls)
    resetar_interface_controle(dss.Reclosers)
    resetar_interface_controle(dss.Relays)


def capturar_estado_base_rede() -> dict:
    return {
        "taps_transformadores": capturar_taps_transformadores(),
        "estados_capacitores": capturar_estados_capacitores(),
    }


def restaurar_estado_base_rede(estado_base: dict, hora_simulacao: float) -> None:
    resetar_controles()
    restaurar_taps_transformadores(estado_base["taps_transformadores"])
    restaurar_estados_capacitores(estado_base["estados_capacitores"])
    executar_comando_dss(f"Set Hour={hora_simulacao}")

    try:
        dss.Solution.InitSnap()
    except Exception:
        pass


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


def obter_tensoes_verbose_por_nivel() -> dict[str, list[dict]]:
    tensoes_mt = []
    tensoes_lv = []

    for nome_barra in list(dss.Circuit.AllBusNames() or []):
        try:
            dss.Circuit.SetActiveBus(nome_barra)
            kv_base = float(dss.Bus.kVBase())
            valores = list(dss.Bus.puVmagAngle() or [])
            nos = list(dss.Bus.Nodes() or [])
        except Exception:
            continue

        if kv_base <= 0:
            continue

        magnitudes = valores[0::2]

        for indice, tensao in enumerate(magnitudes):
            valor = float(tensao)

            if valor < tensao_minima_considerada_pu:
                continue

            no = nos[indice] if indice < len(nos) else None
            registro = {
                "bus": str(nome_barra),
                "node": no,
                "voltage_pu": valor,
                "kv_base": kv_base,
            }

            if kv_base < 1.0:
                tensoes_lv.append(registro)
            else:
                tensoes_mt.append(registro)

    return {
        "mt": tensoes_mt,
        "lv": tensoes_lv,
    }


def resumir_nivel_tensao(registros: list[dict]) -> dict:
    if not registros:
        return {
            "undervoltages": 0,
            "min_voltage": 0.0,
            "overvoltages": 0,
            "max_voltage": 0.0,
            "min_bus": "",
            "max_bus": "",
        }

    registro_minimo = min(registros, key=lambda item: item["voltage_pu"])
    registro_maximo = max(registros, key=lambda item: item["voltage_pu"])

    return {
        "undervoltages": sum(
            1
            for item in registros
            if item["voltage_pu"] < limite_subtensao_pu
        ),
        "min_voltage": registro_minimo["voltage_pu"],
        "overvoltages": sum(
            1
            for item in registros
            if item["voltage_pu"] > limite_sobretensao_pu
        ),
        "max_voltage": registro_maximo["voltage_pu"],
        "min_bus": registro_minimo["bus"],
        "max_bus": registro_maximo["bus"],
    }


def coletar_verbose_tensao(hora_simulacao: float) -> dict:
    tensoes = obter_tensoes_verbose_por_nivel()
    resumo_mt = resumir_nivel_tensao(registros=tensoes["mt"],)
    resumo_lv = resumir_nivel_tensao(registros=tensoes["lv"],)

    return {
        "Hour": hora_simulacao,
        "Undervoltages": resumo_mt["undervoltages"],
        "Min Voltage": resumo_mt["min_voltage"],
        "Overvoltage": resumo_mt["overvoltages"],
        "Max Voltage": resumo_mt["max_voltage"],
        "Min Bus": resumo_mt["min_bus"],
        "Max Bus": resumo_mt["max_bus"],
        "LV Undervoltages": resumo_lv["undervoltages"],
        "Min LV Voltage": resumo_lv["min_voltage"],
        "LV Overvoltage": resumo_lv["overvoltages"],
        "Max LV Voltage": resumo_lv["max_voltage"],
        "Min LV Bus": resumo_lv["min_bus"],
        "Max LV Bus": resumo_lv["max_bus"],
    }

def salvar_verbose_simulacao(
    registros: list[dict],
    diretorio_resultados: Path,
    cenario: dict,
) -> Path:
    diretorio_caso = preparar_diretorio_verbose_opendss(
        diretorio_resultados=diretorio_resultados,
        cenario=cenario,
    )
    sufixo_resultado = montar_sufixo_resultado(cenario=cenario,)
    arquivo_verbose = (
        diretorio_caso
        / f"VoltageExceptions_{sufixo_resultado}.csv"
    )

    with open(arquivo_verbose, "w", encoding="utf-8-sig", newline="") as arquivo:
        writer = csv.DictWriter(
            arquivo,
            fieldnames=[
                "Hour",
                "Undervoltages",
                "Min Voltage",
                "Overvoltage",
                "Max Voltage",
                "Min Bus",
                "Max Bus",
                "LV Undervoltages",
                "Min LV Voltage",
                "LV Overvoltage",
                "Max LV Voltage",
                "Min LV Bus",
                "Max LV Bus",
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


def executar_simulacoes_pool_ev(
    arquivo_dss: Path,
    diretorio_dss_base: Path,
    diretorio_bdgd: Path,
    diretorio_resultados: Path,
    arquivo_checkpoint: Path,
    quantidade_ldv: int,
    quantidade_two_wheelers: int,
    quantidade_trucks: int,
    quantidade_simulacoes: int,
    hora_simulacao: float,
    arquivos_extra_redirect: list[Path] | None = None,
    salvar_arquivos_cenario: bool = False,
    verbose_opendss_completo: bool = True,
) -> list[dict]:
    tempo_inicio_total = time.perf_counter()

    pool_ev = preparar_pool_ev(
        diretorio_dss_base=diretorio_dss_base,
        diretorio_bdgd=diretorio_bdgd,
        diretorio_saida=diretorio_resultados,
        incluir_residencial=(quantidade_ldv + quantidade_two_wheelers) > 0,
        incluir_industrial=quantidade_trucks > 0,
    )

    pool_residencial = pool_ev["pool_residencial"]
    pool_industrial = pool_ev["pool_industrial"]
    arquivo_pool = pool_ev["arquivo_pool"]

    quantidade_residencial = quantidade_ldv + quantidade_two_wheelers

    if quantidade_residencial > len(pool_residencial):
        raise ValueError(
            f"Foram solicitados {quantidade_residencial} veículos residenciais, "
            f"mas existem apenas {len(pool_residencial)} UCBTs residenciais válidas."
        )

    if quantidade_trucks > len(pool_industrial):
        raise ValueError(
            f"Foram solicitados {quantidade_trucks} trucks, "
            f"mas existem apenas {len(pool_industrial)} UCBTs industriais válidas."
        )

    print("")
    print("=" * 80)
    print("PREPARANDO SIMULAÇÕES OPENDSS")
    print("=" * 80)
    print(f"Quantidade de simulações: {quantidade_simulacoes}")
    print(f"Horário: {hora_simulacao:g}h")
    print(f"LDV: {quantidade_ldv}")
    print(f"TW: {quantidade_two_wheelers}")
    print(f"Trucks: {quantidade_trucks}")
    print(f"Pool residencial: {len(pool_residencial)}")
    print(f"Pool industrial: {len(pool_industrial)}")
    print(f"Verbose pós-Solve: {verbose_opendss_completo}")
    print("=" * 80, flush=True)

    tempo_inicio_compilacao = time.perf_counter()

    print("Compilando circuito OpenDSS...", flush=True)

    compilar_circuito_pool(
        arquivo_master=arquivo_dss,
        arquivo_pool_ev=arquivo_pool,
        arquivos_extra_redirect=arquivos_extra_redirect,
    )

    desativar_demand_interval()
    configurar_simulacao_temporal(hora_simulacao=hora_simulacao,)
    executar_solve(hora_simulacao=hora_simulacao,)
    estado_base = capturar_estado_base_rede()
    tempo_compilacao_unica = time.perf_counter() - tempo_inicio_compilacao

    print(
        f"Circuito compilado em {tempo_compilacao_unica:.2f} segundos",
        flush=True,
    )
    print(
        f"Iniciando {quantidade_simulacoes} simulações...",
        flush=True,
    )

    resultados = []

    for numero_simulacao in range(1, quantidade_simulacoes + 1):
        seed_simulacao = gerar_seed_simulacao(numero_simulacao=numero_simulacao,)

        print("")
        print(
            f"[{numero_simulacao}/{quantidade_simulacoes}] "
            f"Iniciando simulação - seed {seed_simulacao}",
            flush=True,
        )

        tempo_inicio_preparacao = time.perf_counter()

        cenario = sortear_cenario_pool_ev(
            pool_residencial=pool_residencial,
            pool_industrial=pool_industrial,
            quantidade_ldv=quantidade_ldv,
            quantidade_two_wheelers=quantidade_two_wheelers,
            quantidade_trucks=quantidade_trucks,
            numero_simulacao=numero_simulacao,
            seed=seed_simulacao,
        )

        arquivo_cenario = None
        diretorio_caso = preparar_diretorio_verbose_opendss(
            diretorio_resultados=diretorio_resultados,
            cenario=cenario,
        )

        if salvar_arquivos_cenario:
            arquivo_cenario_original = salvar_cenario_pool_ev(
                configuracoes_cargas=cenario["configuracoes_cargas"],
                diretorio_saida=diretorio_caso,
                numero_simulacao=numero_simulacao,
                seed=seed_simulacao,
            )
            sufixo_resultado = montar_sufixo_resultado(cenario=cenario,)
            arquivo_cenario = diretorio_caso / f"Cargas_EV_{sufixo_resultado}.dss"
            arquivo_cenario_original = Path(arquivo_cenario_original)

            if arquivo_cenario_original.resolve() != arquivo_cenario.resolve():
                if arquivo_cenario.exists():
                    arquivo_cenario.unlink()
                arquivo_cenario_original.replace(arquivo_cenario)

        cenario["arquivo_cargas_ev"] = arquivo_cenario or arquivo_pool
        cenario["total_pool_valido"] = pool_ev["total_pool_valido"]
        cenario["total_pool_invalido"] = pool_ev["total_pool_invalido"]
        cenario["tempo_preparacao_segundos"] = (
            time.perf_counter() - tempo_inicio_preparacao
        )

        configuracoes_cenario = cenario["configuracoes_cargas"]
        restaurar_estado_base_rede(
            estado_base=estado_base,
            hora_simulacao=hora_simulacao,
        )
        aplicar_cargas_cenario(configuracoes_cargas=configuracoes_cenario,)

        diretorio_verbose = None

        try:
            print(
                f"[{numero_simulacao}/{quantidade_simulacoes}] Executando Solve...",
                flush=True,
            )

            tempo_inicio_solve = time.perf_counter()
            executar_solve(hora_simulacao=hora_simulacao,)
            tempo_solve = time.perf_counter() - tempo_inicio_solve

            print(
                f"[{numero_simulacao}/{quantidade_simulacoes}] "
                f"Solve concluído em {tempo_solve:.2f} segundos",
                flush=True,
            )

            registro_verbose = coletar_verbose_tensao(hora_simulacao=hora_simulacao,)

            if verbose_opendss_completo:
                print(
                    f"[{numero_simulacao}/{quantidade_simulacoes}] "
                    f"Exportando verbose OpenDSS pós-Solve...",
                    flush=True,
                )
                tempo_inicio_verbose = time.perf_counter()
                diretorio_verbose = exportar_verbose_opendss(
                    diretorio_resultados=diretorio_resultados,
                    cenario=cenario,
                )
                tempo_verbose = time.perf_counter() - tempo_inicio_verbose
                print(
                    f"[{numero_simulacao}/{quantidade_simulacoes}] "
                    f"Verbose concluído em {tempo_verbose:.2f} segundos",
                    flush=True,
                )

            resultado = coletar_resumo_simulacao(
                simulacao_global=numero_simulacao,
                total_execucoes=quantidade_simulacoes,
                cenario=cenario,
                quantidade_simulacoes=quantidade_simulacoes,
                hora_simulacao=hora_simulacao,
                tempo_compilacao_segundos=(
                    tempo_compilacao_unica
                    if numero_simulacao == 1
                    else 0.0
                ),
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
            print(f"VoltageExceptions: {arquivo_verbose}")

            if diretorio_verbose is not None:
                print(f"Resultados OpenDSS: {diretorio_verbose}")

            tempo_decorrido = time.perf_counter() - tempo_inicio_total
            media_por_simulacao = tempo_decorrido / numero_simulacao
            tempo_restante = (
                quantidade_simulacoes - numero_simulacao
            ) * media_por_simulacao
            print(
                f"[{numero_simulacao}/{quantidade_simulacoes}] "
                f"Tempo decorrido: {tempo_decorrido:.2f}s | "
                f"Restante estimado: {tempo_restante:.2f}s",
                flush=True,
            )
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
    print(f"Total de cenários: {quantidade_simulacoes}")
    print(f"Pool residencial: {len(pool_residencial)}")
    print(f"Pool industrial: {len(pool_industrial)}")
    print(f"Compilação única: {tempo_compilacao_unica:.2f} segundos")
    print(f"Tempo total: {tempo_total:.2f} segundos")
    print(f"Resumo: {arquivo_resumo}")
    print(f"Checkpoint: {arquivo_checkpoint}")
    print("=" * 80)

    return resultados


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
    salvar_arquivos_cenario: bool = False,
    verbose_opendss_completo: bool = True,
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

        # if quantidade_ldv + quantidade_two_wheelers + quantidade_trucks <= 0:
        #     raise ValueError(
        #         "A quantidade total de veículos deve ser maior que zero."
        #     )

        if diretorio_dss_base is None:
            raise ValueError(
                "diretorio_dss_base é obrigatório para simulação com EV."
            )

        if diretorio_bdgd is None:
            raise ValueError(
                "diretorio_bdgd é obrigatório para simulação com EV."
            )

        if quantidade_simulacoes <= 0:
            raise ValueError(
                "A quantidade de simulações deve ser maior que zero."
            )

        diretorio_resultados = criar_diretorio_resultados(arquivo_dss)
        arquivo_checkpoint = (
            diretorio_resultados
            / "Checkpoint_Simulacoes_OpenDSSDirect.csv"
        )

        return executar_simulacoes_pool_ev(
            arquivo_dss=arquivo_dss,
            diretorio_dss_base=Path(diretorio_dss_base),
            diretorio_bdgd=Path(diretorio_bdgd),
            diretorio_resultados=diretorio_resultados,
            arquivo_checkpoint=arquivo_checkpoint,
            quantidade_ldv=quantidade_ldv,
            quantidade_two_wheelers=quantidade_two_wheelers,
            quantidade_trucks=quantidade_trucks,
            quantidade_simulacoes=quantidade_simulacoes,
            hora_simulacao=hora_simulacao,
            arquivos_extra_redirect=arquivos_extra_redirect,
            salvar_arquivos_cenario=salvar_arquivos_cenario,
            verbose_opendss_completo=verbose_opendss_completo,
        )

    if usar_ev_por_arquivo:
        arquivo_cargas_ev = Path(arquivo_cargas_ev)

        if not arquivo_cargas_ev.exists():
            raise FileNotFoundError(
                f"Arquivo Cargas_EV informado não encontrado:\n"
                f"{arquivo_cargas_ev}"
            )

        quantidade_simulacoes = 1

    if not usar_ev_por_arquivo:
        quantidade_ldv = None
        quantidade_two_wheelers = None
        quantidade_trucks = None
        quantidade_simulacoes = 1

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

    desativar_demand_interval()
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
        diretorio_verbose = None

        try:
            desativar_demand_interval()
            tempo_inicio_solve = time.perf_counter()
            executar_solve(hora_simulacao=hora_simulacao,)
            tempo_solve = time.perf_counter() - tempo_inicio_solve
            registro_verbose = coletar_verbose_tensao(hora_simulacao=hora_simulacao,)

            if verbose_opendss_completo:
                diretorio_verbose = exportar_verbose_opendss(
                    diretorio_resultados=diretorio_resultados,
                    cenario=cenario,
                )

            resultado = coletar_resumo_simulacao(
                simulacao_global=indice_cenario,
                total_execucoes=total_execucoes,
                cenario=cenario,
                quantidade_simulacoes=len(cenarios),
                hora_simulacao=hora_simulacao,
                tempo_compilacao_segundos=(
                    tempo_compilacao_unica
                    if indice_cenario == 1
                    else 0.0
                ),
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
            print(f"VoltageExceptions: {arquivo_verbose}")

            if diretorio_verbose is not None:
                print(f"Resultados OpenDSS: {diretorio_verbose}")
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
