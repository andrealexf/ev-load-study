from pathlib import Path
import re


def normalizar_bus(valor: str) -> str:
    return str(valor or "").strip().strip('"').split(".")[0]


def obter_parametro_linha(
    linha: str,
    parametro: str,
    valor_padrao: str | None = None,
) -> str:
    match = re.search(rf'{parametro}="([^\"]+)"', linha, flags=re.IGNORECASE)

    if match:
        return match.group(1)

    match = re.search(rf"(?:^|\s){parametro}=([^\s!]+)", linha, flags=re.IGNORECASE)

    if match:
        return match.group(1).strip('"')

    if valor_padrao is not None:
        return valor_padrao

    raise ValueError(f"Parâmetro '{parametro}' não encontrado na linha:\n{linha}")


def identificar_tipo_veiculo(linha: str) -> str | None:
    linha_upper = linha.upper()

    match = re.search(r"(?:^|\s)TIPO=(LDV|TW|TRUCK|BUS)(?:\s|$)", linha_upper)

    if match:
        return match.group(1)

    if "LOAD.BUS_" in linha_upper or "LOAD.EVPOOL_BUS_" in linha_upper:
        return "BUS"

    if "LOAD.LDV_" in linha_upper or "LOAD.EVPOOL_LDV_" in linha_upper:
        return "LDV"

    if "LOAD.TW_" in linha_upper or "LOAD.EVPOOL_TW_" in linha_upper:
        return "TW"

    if "LOAD.TRUCK_" in linha_upper or "LOAD.EVPOOL_TRUCK_" in linha_upper:
        return "TRUCK"

    return None


def identificar_cor_busmarker(linha: str) -> str | None:
    tipo = identificar_tipo_veiculo(linha=linha,)

    if tipo == "LDV":
        return "Red"

    if tipo == "TW":
        return "Green"

    if tipo == "TRUCK":
        return "Fuchsia"

    if tipo == "BUS":
        return "Yellow"

    return None


def localizar_arquivo_rede(
    diretorio_dss_base: Path,
    prefixo: str,
    alimentador: str,
) -> Path | None:
    diretorio_dss_base = Path(diretorio_dss_base)
    alimentador = str(alimentador or "").strip().upper()

    if not alimentador:
        return None

    padroes = [
        f"{prefixo}_DU01_2022124950_{alimentador}_--MBS-1--T--.dss",
        f"{prefixo}_*_{alimentador}_*.dss",
        f"{prefixo}_*{alimentador}*.dss",
    ]

    for padrao in padroes:
        arquivos = sorted(diretorio_dss_base.glob(padrao))

        if arquivos:
            return arquivos[0]

    return None


def ler_conexoes_dss(arquivo_dss: Path) -> list[tuple[str, str]]:
    conexoes = []

    with open(arquivo_dss, "r", encoding="utf-8", errors="ignore") as arquivo:
        for linha in arquivo:
            try:
                bus1 = normalizar_bus(obter_parametro_linha(linha, "bus1"))
                bus2 = normalizar_bus(obter_parametro_linha(linha, "bus2"))
            except Exception:
                continue

            if bus1 and bus2:
                conexoes.append((bus1, bus2))

    return conexoes


def localizar_bus_marker_rede(
    bus_carga: str,
    alimentador: str,
    diretorio_dss_base: Path,
) -> str:
    bus_atual = normalizar_bus(bus_carga)

    arquivo_ramais = localizar_arquivo_rede(
        diretorio_dss_base=diretorio_dss_base,
        prefixo="RamaisBT",
        alimentador=alimentador,
    )
    arquivo_segmentos = localizar_arquivo_rede(
        diretorio_dss_base=diretorio_dss_base,
        prefixo="SegmentosBT",
        alimentador=alimentador,
    )

    if arquivo_ramais is None or arquivo_segmentos is None:
        return bus_atual

    ramais = ler_conexoes_dss(arquivo_dss=arquivo_ramais,)
    segmentos = ler_conexoes_dss(arquivo_dss=arquivo_segmentos,)
    visitados = set()

    while bus_atual and bus_atual not in visitados:
        visitados.add(bus_atual)
        candidatos = [bus1 for bus1, bus2 in ramais if bus2 == bus_atual]

        if not candidatos:
            break

        proximo_bus = candidatos[0]

        if proximo_bus == bus_atual:
            break

        bus_atual = proximo_bus

    for bus1, bus2 in segmentos:
        if bus2 == bus_atual:
            return bus1

    return bus_atual


def executar_add_bus_marker(
    arquivo_cargas_ev: Path,
    diretorio_dss_base: Path,
    arquivo_saida: Path | None = None,
) -> Path:
    arquivo_cargas_ev = Path(arquivo_cargas_ev)
    diretorio_dss_base = Path(diretorio_dss_base)

    if not arquivo_cargas_ev.exists():
        raise FileNotFoundError(f"Arquivo de cargas EV não encontrado:\n{arquivo_cargas_ev}")

    if arquivo_saida is None:
        arquivo_saida = arquivo_cargas_ev.parent / "BusMarkers_EV.dss"
    else:
        arquivo_saida = Path(arquivo_saida)

    marcadores = []
    chaves_vistas = set()

    with open(arquivo_cargas_ev, "r", encoding="utf-8", errors="ignore") as arquivo:
        for linha in arquivo:
            tipo = identificar_tipo_veiculo(linha=linha,)
            cor = identificar_cor_busmarker(linha=linha,)

            if tipo is None or cor is None:
                continue

            try:
                bus1 = obter_parametro_linha(linha, "bus1")
            except Exception:
                continue

            alimentador = obter_parametro_linha(linha, "ctmt", "")

            if tipo == "BUS":
                bus_marker = normalizar_bus(bus1)
            else:
                bus_marker = localizar_bus_marker_rede(
                    bus_carga=bus1,
                    alimentador=alimentador,
                    diretorio_dss_base=diretorio_dss_base,
                )

            if not bus_marker:
                continue

            chave = (bus_marker.upper(), cor.upper())

            if chave in chaves_vistas:
                continue

            chaves_vistas.add(chave)
            marcadores.append(
                f'AddBusMarker Bus="{bus_marker}" code=15 color={cor} size=4'
            )

    arquivo_saida.parent.mkdir(parents=True, exist_ok=True)

    with open(arquivo_saida, "w", encoding="utf-8") as arquivo:
        for marcador in marcadores:
            arquivo.write(marcador + "\n")

    return arquivo_saida
