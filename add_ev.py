from pathlib import Path
import csv
import random
import re


DIRETORIO_CODIGO = Path(__file__).resolve().parent

ARQUIVO_ENTRADA_EV = (
    DIRETORIO_CODIGO / "CargasBT_DU10_2022124950_IJAU11_--MBS-1--T--.dss"
)

ARQUIVO_SAIDA_EV = (
    DIRETORIO_CODIGO / "Cargas_EV.dss"
)

ARQUIVO_TXT_RAMAIS = (
    DIRETORIO_CODIGO / "Loads_UCBT_IJAU11.txt"
)


def normalizar_codigo(valor) -> str:
    if valor is None:
        return ""

    texto = str(valor).strip()

    if texto.endswith(".0"):
        texto = texto[:-2]

    texto = texto.replace(" ", "")

    return texto


def ler_ramais_arquivo(
    arquivo_ramais: Path,
) -> list[str]:
    if not arquivo_ramais.exists():
        raise FileNotFoundError(f"Arquivo de RAMAIS não encontrado: {arquivo_ramais}")

    ramais = []
    ramais_vistos = set()

    with open(arquivo_ramais, "r", encoding="utf-8-sig", newline="") as arquivo:
        amostra = arquivo.read(4096)
        arquivo.seek(0)

        try:
            dialect = csv.Sniffer().sniff(amostra, delimiters=";,\t")
        except csv.Error:
            dialect = csv.excel
            dialect.delimiter = ";"

        leitor = csv.reader(arquivo, dialect)

        for linha in leitor:
            if not linha:
                continue

            primeiro_campo = normalizar_codigo(linha[0])

            if not primeiro_campo:
                continue

            if primeiro_campo.upper() in {"RAMAL", "COD_ID", "ID"}:
                continue

            if primeiro_campo in ramais_vistos:
                continue

            ramais.append(primeiro_campo)
            ramais_vistos.add(primeiro_campo)

    return ramais


def extrair_nome_carga(linha: str) -> str | None:
    match = re.search(r'"Load\.([^"]+)"', linha)

    if not match:
        return None

    return match.group(1)


def extrair_carga_base(nome_carga: str) -> str:
    return re.sub(r"_M\d+$", "", nome_carga)


def extrair_ramal_da_carga_base(carga_base: str) -> str:
    texto = str(carga_base).strip()

    if texto.upper().startswith("BT_"):
        texto = texto[3:]

    texto = re.sub(r"_\d+$", "", texto)

    return normalizar_codigo(texto)


def obter_ordem_carga_base(carga_base: str) -> int:
    texto = str(carga_base).strip()

    if texto.upper().startswith("BT_"):
        texto = texto[3:]

    partes = texto.rsplit("_", 1)

    if len(partes) == 2 and partes[1].isdigit():
        return int(partes[1])

    return 0


def obter_parametro_linha(
    linha: str,
    parametro: str,
    valor_padrao: str | None = None,
) -> str:
    padrao_com_aspas = rf'{parametro}="([^"]+)"'
    match = re.search(padrao_com_aspas, linha, flags=re.IGNORECASE)

    if match:
        return match.group(1)

    padrao_sem_aspas = rf"{parametro}=([^\s]+)"
    match = re.search(padrao_sem_aspas, linha, flags=re.IGNORECASE)

    if match:
        return match.group(1)

    if valor_padrao is not None:
        return valor_padrao

    raise ValueError(f"Parâmetro '{parametro}' não encontrado na linha:\n{linha}")


def ler_cargas_por_ramal(
    arquivo_entrada: Path,
) -> dict[str, list[str]]:
    if not arquivo_entrada.exists():
        raise FileNotFoundError(f"Arquivo de entrada não encontrado: {arquivo_entrada}")

    cargas_temp: dict[str, dict[str, list[str]]] = {}

    with open(arquivo_entrada, "r", encoding="utf-8") as arquivo:
        for linha in arquivo:
            nome_carga = extrair_nome_carga(linha)

            if not nome_carga:
                continue

            carga_base = extrair_carga_base(nome_carga)
            ramal = extrair_ramal_da_carga_base(carga_base)

            if not ramal:
                continue

            if ramal not in cargas_temp:
                cargas_temp[ramal] = {}

            if carga_base not in cargas_temp[ramal]:
                cargas_temp[ramal][carga_base] = []

            cargas_temp[ramal][carga_base].append(linha)

    cargas_por_ramal: dict[str, list[str]] = {}

    for ramal, cargas_base in cargas_temp.items():
        carga_base_escolhida = sorted(
            cargas_base.keys(),
            key=lambda carga: (
                obter_ordem_carga_base(carga),
                carga,
            ),
        )[0]

        cargas_por_ramal[ramal] = cargas_base[carga_base_escolhida]

    return cargas_por_ramal


def montar_linha_ev(
    linha_original: str,
    kw_ev: float,
    daily_ev: str,
) -> str:
    nome_carga = extrair_nome_carga(linha_original)

    if not nome_carga:
        raise ValueError(f"Nome da carga não encontrado:\n{linha_original}")

    bus1 = obter_parametro_linha(linha_original, "bus1")
    conn = obter_parametro_linha(linha_original, "conn", "wye")
    model = obter_parametro_linha(linha_original, "model", "1")
    kv = obter_parametro_linha(linha_original, "kv")

    phases = 3 if bus1.endswith(".1.2.3.4") else 1

    linha_ev = (
        f'New "Load.EV_{nome_carga}" '
        f'bus1="{bus1}" '
        f"phases={phases} "
        f"conn={conn} "
        f"model={model} "
        f"kv={kv} "
        f"kw={kw_ev} "
        f"pf=0.92 "
        f"status=variable "
        f"vmaxpu=1.5 "
        f"vminpu=0.92 "
        f'daily="{daily_ev}"'
    )

    return linha_ev


def selecionar_ramais_aleatorios_validos(
    ramais_arquivo: list[str],
    cargas_por_ramal: dict[str, list[str]],
    quantidade: int,
) -> tuple[list[str], list[str]]:
    if quantidade <= 0:
        raise ValueError("A quantidade precisa ser maior que zero.")

    ramais_validos = [
        ramal for ramal in ramais_arquivo
        if ramal in cargas_por_ramal
    ]

    ramais_invalidos = [
        ramal for ramal in ramais_arquivo
        if ramal not in cargas_por_ramal
    ]

    if len(ramais_validos) < quantidade:
        #print("\nRAMAIS não encontrados no DSS:")
        for ramal in ramais_invalidos:
            print(f"- {ramal}")

        raise ValueError(
            f"Existem apenas {len(ramais_validos)} RAMAIS válidos no DSS, "
            f"mas foram solicitadas {quantidade} unidades EV."
        )

    ramais_sorteados = random.sample(ramais_validos, quantidade)

    return ramais_sorteados, ramais_invalidos


def gerar_arquivo_ev(
    arquivo_entrada: Path,
    arquivo_saida: Path,
    arquivo_ramais: Path,
    quantidade: int,
    daily_ev: str = "EV_1",
    kw_total_por_unidade: float = 3.5,
) -> None:
    ramais_arquivo = ler_ramais_arquivo(
        arquivo_ramais=arquivo_ramais,
    )

    if not ramais_arquivo:
        raise ValueError(f"Nenhum RAMAL encontrado no arquivo: {arquivo_ramais}")

    cargas_por_ramal = ler_cargas_por_ramal(
        arquivo_entrada=arquivo_entrada,
    )

    ramais_sorteados, ramais_invalidos = selecionar_ramais_aleatorios_validos(
        ramais_arquivo=ramais_arquivo,
        cargas_por_ramal=cargas_por_ramal,
        quantidade=quantidade,
    )

    #print(f"\nDEBUG - Quantidade solicitada: {quantidade}")
    #print(f"DEBUG - Total de RAMAIS sorteados: {len(ramais_sorteados)}")

    linhas_ev = []

    for ramal in ramais_sorteados:
        linhas_carga = cargas_por_ramal[ramal]

        kw_ev = kw_total_por_unidade / len(linhas_carga)

        for linha_original in linhas_carga:
            linha_ev = montar_linha_ev(
                linha_original=linha_original,
                kw_ev=kw_ev,
                daily_ev=daily_ev,
            )

            linhas_ev.append(linha_ev)

    if not linhas_ev:
        raise ValueError("Nenhuma linha EV foi gerada.")

    arquivo_saida.parent.mkdir(parents=True, exist_ok=True)

    with open(arquivo_saida, "w", encoding="utf-8") as arquivo:
        for linha in linhas_ev:
            arquivo.write(linha + "\n")

    ramais_validos_total = len(
        [
            ramal for ramal in ramais_arquivo
            if ramal in cargas_por_ramal
        ]
    )


    print(f"Arquivo de saída: {arquivo_saida}")
    #print(f"RAMAIS disponíveis no arquivo: {len(ramais_arquivo)}")
    #print(f"RAMAIS válidos no DSS: {ramais_validos_total}")
    print(f"Unidades EV criadas: {len(ramais_sorteados)}")
    print(f"Linhas Load.EV criadas: {len(linhas_ev)}")

    print("\nRAMAIS selecionados para receber unidade EV:")
    print(f"Total selecionado: {len(ramais_sorteados)}")

    for indice, ramal in enumerate(ramais_sorteados, start=1):
        print(f"EV {indice}: RAMAL {ramal}")

    print("")
    print(f"Total não encontrado: {len(ramais_invalidos)}")


def executar_add_ev(quantidade: int) -> None:
    gerar_arquivo_ev(
        arquivo_entrada=ARQUIVO_ENTRADA_EV,
        arquivo_saida=ARQUIVO_SAIDA_EV,
        arquivo_ramais=ARQUIVO_TXT_RAMAIS,
        quantidade=quantidade,
        daily_ev="EV_1",
        kw_total_por_unidade=3.5,
    )

