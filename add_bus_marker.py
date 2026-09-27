from pathlib import Path
import re


def obter_parametro_linha_dss(
    linha: str,
    parametro: str,
    valor_padrao: str | None = None,
) -> str | None:
    match = re.search(
        rf'{parametro}="([^"]+)"',
        linha,
        flags=re.IGNORECASE,
    )

    if match:
        return match.group(1)

    match = re.search(
        rf"{parametro}=([^\s]+)",
        linha,
        flags=re.IGNORECASE,
    )

    if match:
        return match.group(1)

    return valor_padrao


def extrair_bus1_linha_load(
    linha: str,
) -> str | None:
    return obter_parametro_linha_dss(
        linha=linha,
        parametro="bus1",
    )


def obter_barra_sem_nos(
    bus: str | None,
) -> str:
    if not bus:
        return ""

    return str(bus).strip().split(".")[0]


def identificar_cor_busmarker(
    linha: str,
) -> str | None:
    linha_upper = linha.upper()

    if '"LOAD.LDV_' in linha_upper:
        return "Red"

    if "LOAD.LDV_" in linha_upper:
        return "Red"

    if "TIPO=LDV" in linha_upper:
        return "Red"

    if '"LOAD.TW_' in linha_upper:
        return "Green"

    if "LOAD.TW_" in linha_upper:
        return "Green"

    if "TIPO=TW" in linha_upper:
        return "Green"

    if '"LOAD.TRUCK_' in linha_upper:
        return "Fuchsia"

    if "LOAD.TRUCK_" in linha_upper:
        return "Fuchsia"

    if "TIPO=TRUCK" in linha_upper:
        return "Fuchsia"

    return None


def extrair_ctmt_linha_ev(
    linha: str,
) -> str:
    match = re.search(
        r"(?:^|\s)ctmt=([A-Za-z0-9_]+)",
        linha,
        flags=re.IGNORECASE,
    )

    if not match:
        return ""

    return match.group(1).strip().upper()


def extrair_alimentador_cabecalho(
    linha: str,
) -> str:
    match = re.search(
        r"ALIMENTADOR\s+([A-Za-z0-9_]+)",
        linha,
        flags=re.IGNORECASE,
    )

    if not match:
        return ""

    return match.group(1).strip().upper()


def localizar_arquivo_rede_bt(
    diretorio_dss_base: Path,
    prefixo: str,
    alimentador: str,
) -> Path:
    diretorio_dss_base = Path(diretorio_dss_base)
    alimentador = str(alimentador).strip().upper()
    prefixo = str(prefixo).strip()

    padroes = [
        f"{prefixo}_DU01_2022124950_{alimentador}_--MBS-1--T--.dss",
        f"{prefixo}_*_{alimentador}_*.dss",
        f"{prefixo}_*{alimentador}*.dss",
    ]

    arquivos_encontrados = []

    for padrao in padroes:
        arquivos_encontrados.extend(
            sorted(
                diretorio_dss_base.glob(padrao)
            )
        )

    arquivos_unicos = []
    caminhos_vistos = set()

    for arquivo in arquivos_encontrados:
        caminho = arquivo.resolve()

        if caminho in caminhos_vistos:
            continue

        caminhos_vistos.add(caminho)
        arquivos_unicos.append(arquivo)

    if not arquivos_unicos:
        raise FileNotFoundError(
            f"Arquivo {prefixo} não encontrado para {alimentador}.\n"
            f"Diretório verificado:\n{diretorio_dss_base}"
        )

    return arquivos_unicos[0]


def ler_indice_linhas_por_bus2(
    arquivo_dss: Path,
) -> dict[str, list[dict]]:
    indice = {}

    with open(
        arquivo_dss,
        "r",
        encoding="utf-8",
        errors="ignore",
    ) as arquivo:
        for linha in arquivo:
            linha_original = linha.strip()

            if not linha_original:
                continue

            if not linha_original.upper().startswith("NEW "):
                continue

            bus1 = obter_parametro_linha_dss(
                linha=linha_original,
                parametro="bus1",
            )

            bus2 = obter_parametro_linha_dss(
                linha=linha_original,
                parametro="bus2",
            )

            if not bus1 or not bus2:
                continue

            bus1_base = obter_barra_sem_nos(bus1)
            bus2_base = obter_barra_sem_nos(bus2)

            if not bus1_base or not bus2_base:
                continue

            registro = {
                "bus1": bus1_base,
                "bus2": bus2_base,
                "linha": linha_original,
            }

            if bus2_base not in indice:
                indice[bus2_base] = []

            indice[bus2_base].append(registro)

    return indice


def encontrar_primeiro_bus1_ramais(
    bus_carga: str,
    indice_ramais_por_bus2: dict[str, list[dict]],
) -> str | None:
    bus_atual = obter_barra_sem_nos(bus_carga)
    visitados = set()

    while True:
        if not bus_atual:
            return None

        if bus_atual in visitados:
            return None

        visitados.add(bus_atual)

        ramais = indice_ramais_por_bus2.get(bus_atual)

        if not ramais:
            return bus_atual

        ramal = ramais[0]
        bus_atual = ramal["bus1"]


def encontrar_primeiro_bus1_segmento_bt(
    bus_inicio: str,
    indice_segmentos_por_bus2: dict[str, list[dict]],
) -> str | None:
    bus_atual = obter_barra_sem_nos(bus_inicio)

    if not bus_atual:
        return None

    segmentos = indice_segmentos_por_bus2.get(bus_atual)

    if not segmentos:
        return None

    segmento = segmentos[0]

    return segmento["bus1"]


def carregar_indices_rede_bt(
    diretorio_dss_base: Path,
    alimentador: str,
    cache_indices: dict,
) -> tuple[
    dict[str, list[dict]],
    dict[str, list[dict]],
]:
    alimentador = str(alimentador).strip().upper()

    if alimentador in cache_indices:
        return cache_indices[alimentador]

    arquivo_ramais = localizar_arquivo_rede_bt(
        diretorio_dss_base=diretorio_dss_base,
        prefixo="RamaisBT",
        alimentador=alimentador,
    )

    arquivo_segmentos = localizar_arquivo_rede_bt(
        diretorio_dss_base=diretorio_dss_base,
        prefixo="SegmentosBT",
        alimentador=alimentador,
    )

    indice_ramais = ler_indice_linhas_por_bus2(
        arquivo_dss=arquivo_ramais,
    )

    indice_segmentos = ler_indice_linhas_por_bus2(
        arquivo_dss=arquivo_segmentos,
    )

    cache_indices[alimentador] = (
        indice_ramais,
        indice_segmentos,
    )

    return indice_ramais, indice_segmentos


def definir_arquivo_saida_busmarker(
    arquivo_cargas_ev: Path,
    arquivo_saida: Path | None = None,
) -> Path:
    if arquivo_saida is not None:
        return Path(arquivo_saida)

    nome_saida = arquivo_cargas_ev.name.replace(
        "Cargas_EV",
        "BusMarkers_EV",
    )

    return arquivo_cargas_ev.parent / nome_saida


def executar_add_bus_marker(
    arquivo_cargas_ev: Path,
    diretorio_dss_base: Path,
    arquivo_saida: Path | None = None,
) -> Path:
    arquivo_cargas_ev = Path(arquivo_cargas_ev)
    diretorio_dss_base = Path(diretorio_dss_base)

    if not arquivo_cargas_ev.exists():
        raise FileNotFoundError(
            f"Arquivo Cargas_EV não encontrado:\n{arquivo_cargas_ev}"
        )

    arquivo_busmarkers = definir_arquivo_saida_busmarker(
        arquivo_cargas_ev=arquivo_cargas_ev,
        arquivo_saida=arquivo_saida,
    )

    markers = []
    chaves_usadas = set()
    cache_indices = {}
    alimentador_atual = ""

    with open(
        arquivo_cargas_ev,
        "r",
        encoding="utf-8",
        errors="ignore",
    ) as arquivo:
        for linha in arquivo:
            linha = linha.strip()

            if not linha:
                continue

            if linha.startswith("!"):
                alimentador_cabecalho = extrair_alimentador_cabecalho(
                    linha=linha,
                )

                if alimentador_cabecalho:
                    alimentador_atual = alimentador_cabecalho

                continue

            if not linha.upper().startswith("NEW "):
                continue

            cor = identificar_cor_busmarker(
                linha=linha,
            )

            if cor is None:
                continue

            bus1_carga = extrair_bus1_linha_load(
                linha=linha,
            )

            if not bus1_carga:
                continue

            alimentador = extrair_ctmt_linha_ev(
                linha=linha,
            )

            if not alimentador:
                alimentador = alimentador_atual

            if not alimentador:
                continue

            indice_ramais, indice_segmentos = carregar_indices_rede_bt(
                diretorio_dss_base=diretorio_dss_base,
                alimentador=alimentador,
                cache_indices=cache_indices,
            )

            primeiro_bus1_ramais = encontrar_primeiro_bus1_ramais(
                bus_carga=bus1_carga,
                indice_ramais_por_bus2=indice_ramais,
            )

            if not primeiro_bus1_ramais:
                continue

            primeiro_bus1_segmento = encontrar_primeiro_bus1_segmento_bt(
                bus_inicio=primeiro_bus1_ramais,
                indice_segmentos_por_bus2=indice_segmentos,
            )

            if not primeiro_bus1_segmento:
                continue

            chave = (
                primeiro_bus1_segmento,
                cor,
            )

            if chave in chaves_usadas:
                continue

            chaves_usadas.add(chave)

            markers.append(
                {
                    "bus": primeiro_bus1_segmento,
                    "cor": cor,
                    "alimentador": alimentador,
                }
            )

    arquivo_busmarkers.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        arquivo_busmarkers,
        "w",
        encoding="utf-8",
    ) as arquivo:
        arquivo.write("! Arquivo gerado automaticamente.\n")
        arquivo.write("! Marcadores posicionados no primeiro SegmentosBT encontrado a montante da carga EV.\n")
        arquivo.write("! Este arquivo é apenas para visualização e não é redirecionado na simulação elétrica.\n\n")

        for marker in markers:
            arquivo.write(
                f'AddBusMarker Bus="{marker["bus"]}" '
                f"code=15 "
                f'color={marker["cor"]} '
                f"size=4 "
                f'! alimentador={marker["alimentador"]}\n'
            )

    return arquivo_busmarkers