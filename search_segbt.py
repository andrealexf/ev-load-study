from pathlib import Path
import csv
import re

DIRETORIO_CODIGO = Path(__file__).resolve().parent

ARQUIVO_CARGAS_EV = DIRETORIO_CODIGO / "Cargas_EV.dss"

ARQUIVO_RAMAIS_BT = (
    DIRETORIO_CODIGO / "RamaisBT_2022124950_IJAU11_--MBS-1--T--.dss"
)

ARQUIVO_SEGMENTOS_BT = (
    DIRETORIO_CODIGO / "SegmentosBT_2022124950_IJAU11_--MBS-1--T--.dss"
)

ARQUIVO_SAIDA = DIRETORIO_CODIGO / "resultado_search_segbt.csv"


def normalizar_bus(valor: str) -> str:
    """
    Remove as fases do barramento.

    Exemplo:
    4000994308.1.4     -> 4000994308
    715617.1.4         -> 715617
    715617.1.2.3.4     -> 715617
    """
    if valor is None:
        return ""

    bus = str(valor).strip().replace('"', "")

    # Remove sufixo de fases
    bus = re.sub(r"(\.\d+)+$", "", bus)

    return bus.strip()


def extrair_parametro_linha(
    linha: str,
    parametro: str,
) -> str | None:
    """
    Extrai parâmetros do OpenDSS de forma robusta.

    Aceita:
    bus1="715617.1.4"
    bus1 = "715617.1.4"
    bus1=715617.1.4
    """
    parametro_regex = re.escape(parametro)

    padrao_com_aspas = rf"\b{parametro_regex}\s*=\s*\"([^\"]+)\""
    match = re.search(padrao_com_aspas, linha, flags=re.IGNORECASE)

    if match:
        return match.group(1).strip()

    padrao_sem_aspas = rf"\b{parametro_regex}\s*=\s*([^\s]+)"
    match = re.search(padrao_sem_aspas, linha, flags=re.IGNORECASE)

    if match:
        return match.group(1).strip().replace('"', "")

    return None


def extrair_nome_load(linha: str) -> str | None:
    """
    Extrai o nome da carga.

    Exemplo:
    New "Load.EV_BT_994308_M1" ...
    retorna:
    EV_BT_994308_M1
    """
    match = re.search(r'"Load\.([^"]+)"', linha, flags=re.IGNORECASE)

    if match:
        return match.group(1)

    return None


def extrair_nome_line(linha: str) -> str | None:
    """
    Extrai o nome da linha.

    Exemplo:
    New "Line.RBT_994308" ...
    retorna:
    RBT_994308
    """
    match = re.search(r'"Line\.([^"]+)"', linha, flags=re.IGNORECASE)

    if match:
        return match.group(1)

    return None


def extrair_ramal_de_nome_load(nome_load: str) -> str:
    texto = str(nome_load).strip()

    prefixos_ev = [
        "EV_",
        "LDV_",
        "TW_",
        "TWO_WHEELER_",
        "TWO_WHEELERS_",
    ]

    for prefixo in prefixos_ev:
        if texto.upper().startswith(prefixo):
            texto = texto[len(prefixo):]
            break

    if texto.upper().startswith("BT_"):
        texto = texto[3:]

    texto = re.sub(r"_M\d+$", "", texto, flags=re.IGNORECASE)

    texto = re.sub(r"_\d+$", "", texto)

    return texto.strip()


def extrair_ramal_de_nome_line(nome_line: str) -> str:
    """
    Extrai o RAMAL a partir do nome da linha do RamaisBT.

    Exemplo:
    RBT_994308 -> 994308
    """
    texto = str(nome_line).strip()

    if texto.upper().startswith("RBT_"):
        texto = texto[4:]

    return texto.strip()


def ler_cargas_ev(
    arquivo_cargas_ev: Path,
) -> list[dict]:
    """
    Lê o arquivo Cargas_EV.dss e retorna as cargas EV com seus barramentos.
    """
    if not arquivo_cargas_ev.exists():
        raise FileNotFoundError(f"Arquivo de cargas EV não encontrado: {arquivo_cargas_ev}")

    cargas = []

    with open(arquivo_cargas_ev, "r", encoding="utf-8") as arquivo:
        for linha in arquivo:
            nome_load = extrair_nome_load(linha)

            if not nome_load:
                continue

            bus1 = extrair_parametro_linha(linha, "bus1")

            if not bus1:
                continue

            ramal = extrair_ramal_de_nome_load(nome_load)

            cargas.append(
                {
                    "nome_load": nome_load,
                    "ramal": ramal,
                    "bus_carga_original": bus1,
                    "bus_carga": normalizar_bus(bus1),
                    "linha_original": linha.strip(),
                }
            )

    return cargas


def ler_linhas_bus1_bus2(
    arquivo_dss: Path,
) -> list[dict]:
    """
    Lê um arquivo DSS com objetos Line que possuem bus1 e bus2.
    """
    if not arquivo_dss.exists():
        raise FileNotFoundError(f"Arquivo DSS não encontrado: {arquivo_dss}")

    linhas = []

    with open(arquivo_dss, "r", encoding="utf-8") as arquivo:
        for numero_linha, linha in enumerate(arquivo, start=1):
            nome_line = extrair_nome_line(linha)
            bus1 = extrair_parametro_linha(linha, "bus1")
            bus2 = extrair_parametro_linha(linha, "bus2")

            if not bus1 or not bus2:
                continue

            ramal = ""

            if nome_line and nome_line.upper().startswith("RBT_"):
                ramal = extrair_ramal_de_nome_line(nome_line)

            linhas.append(
                {
                    "numero_linha": numero_linha,
                    "nome_line": nome_line or "",
                    "ramal": ramal,
                    "bus1_original": bus1,
                    "bus2_original": bus2,
                    "bus1": normalizar_bus(bus1),
                    "bus2": normalizar_bus(bus2),
                    "linha_original": linha.strip(),
                }
            )

    return linhas


def criar_indice_por_bus2(
    linhas: list[dict],
) -> dict[str, list[dict]]:
    """
    Cria índice para busca por bus2.
    """
    indice = {}

    for item in linhas:
        bus2 = item["bus2"]

        if bus2 not in indice:
            indice[bus2] = []

        indice[bus2].append(item)

    return indice


def criar_indice_ramal_rbt(
    linhas_ramais: list[dict],
) -> dict[str, dict]:
    """
    Cria índice dos RamaisBT pelo RAMAL.

    Exemplo:
    Line.RBT_994308 -> chave 994308
    """
    indice = {}

    for item in linhas_ramais:
        ramal = item.get("ramal", "")

        if not ramal:
            continue

        if ramal not in indice:
            indice[ramal] = item

    return indice


def encontrar_primeiro_bus1_segmento(
    bus_inicial_segmento: str,
    indice_segmentos_por_bus2: dict[str, list[dict]],
) -> tuple[str | None, list[dict]]:
    """
    Sobe a rede BT usando SegmentosBT.

    Regra:
    - bus_inicial_segmento é o bus1 do RamaisBT;
    - esse bus deve ser procurado como bus2 no SegmentosBT;
    - o bus1 encontrado vira o próximo bus a procurar como bus2;
    - continua até não encontrar mais segmento.
    """
    bus_atual = bus_inicial_segmento
    caminho = []
    visitados = set()

    while True:
        if bus_atual in visitados:
            print(f"Aviso: ciclo detectado no bus {bus_atual}. Interrompendo busca.")
            break

        visitados.add(bus_atual)

        segmentos = indice_segmentos_por_bus2.get(bus_atual)

        if not segmentos:
            break

        segmento = segmentos[0]

        caminho.append(segmento)

        bus_atual = segmento["bus1"]

    if not caminho:
        return None, caminho

    primeiro_bus1 = caminho[-1]["bus1"]

    return primeiro_bus1, caminho

def encontrar_primeiro_bus1_ramais(
    bus_carga: str,
    indice_ramais_por_bus2: dict[str, list[dict]],
) -> tuple[str | None, list[dict]]:
    """
    Sobe a rede usando RamaisBT.

    Regra:
    - começa pelo bus da carga;
    - procura em RamaisBT onde bus2 = bus atual;
    - pega o bus1 encontrado;
    - esse bus1 vira o novo bus atual;
    - repete enquanto o novo bus atual também aparecer como bus2 em RamaisBT.

    Exemplo:
    1000994308 -> 4000994308 -> 715617
    """
    bus_atual = bus_carga
    caminho = []
    visitados = set()

    while True:
        if bus_atual in visitados:
            print(f"Aviso: ciclo detectado em RamaisBT no bus {bus_atual}.")
            break

        visitados.add(bus_atual)

        ramais = indice_ramais_por_bus2.get(bus_atual)

        if not ramais:
            break

        # Se existir mais de uma linha com o mesmo bus2, usa a primeira
        ramal = ramais[0]

        caminho.append(ramal)

        bus_atual = ramal["bus1"]

    if not caminho:
        return None, caminho

    primeiro_bus1_ramais = caminho[-1]["bus1"]

    return primeiro_bus1_ramais, caminho


def buscar_segbt_para_cargas_ev(
    arquivo_cargas_ev: Path,
    arquivo_ramais_bt: Path,
    arquivo_segmentos_bt: Path,
) -> list[dict]:
    """
    Para cada carga EV:
    1. pega o bus da carga;
    2. sobe em RamaisBT procurando bus atual como bus2;
    3. quando não encontrar mais em RamaisBT, pega o último bus1 encontrado;
    4. usa esse último bus1 para procurar em SegmentosBT como bus2;
    5. sobe em SegmentosBT até o primeiro bus1 possível.
    """
    cargas_ev = ler_cargas_ev(arquivo_cargas_ev)
    ramais_bt = ler_linhas_bus1_bus2(arquivo_ramais_bt)
    segmentos_bt = ler_linhas_bus1_bus2(arquivo_segmentos_bt)

    indice_ramais_por_bus2 = criar_indice_por_bus2(ramais_bt)
    indice_segmentos_por_bus2 = criar_indice_por_bus2(segmentos_bt)

    resultados = []

    for carga in cargas_ev:
        nome_load = carga["nome_load"]
        ramal_carga = carga["ramal"]
        bus_carga = carga["bus_carga"]

        primeiro_bus1_ramais, caminho_ramais = encontrar_primeiro_bus1_ramais(
            bus_carga=bus_carga,
            indice_ramais_por_bus2=indice_ramais_por_bus2,
        )

        if not primeiro_bus1_ramais:
            resultados.append(
                {
                    "nome_load": nome_load,
                    "ramal": ramal_carga,
                    "bus_carga": bus_carga,
                    "ramal_bus1": "",
                    "ramal_bus2": "",
                    "primeiro_bus1_ramais": "",
                    "qtd_ramais_percorridos": 0,
                    "segmento_bus1_direto": "",
                    "primeiro_bus1_segmento": "",
                    "qtd_segmentos_percorridos": 0,
                    "status": "RAMAL_NAO_ENCONTRADO",
                }
            )
            continue

        primeiro_ramal = caminho_ramais[0]
        ultimo_ramal = caminho_ramais[-1]

        primeiro_bus1_segmento, caminho_segmentos = encontrar_primeiro_bus1_segmento(
            bus_inicial_segmento=primeiro_bus1_ramais,
            indice_segmentos_por_bus2=indice_segmentos_por_bus2,
        )

        if caminho_segmentos:
            segmento_bus1_direto = caminho_segmentos[0]["bus1"]
        else:
            segmento_bus1_direto = ""

        if primeiro_bus1_segmento:
            status = "OK"
        else:
            status = "SEGMENTO_NAO_ENCONTRADO"

        resultados.append(
            {
                "nome_load": nome_load,
                "ramal": ramal_carga,
                "bus_carga": bus_carga,

                # Primeiro RamaisBT encontrado a partir da carga
                "ramal_bus1": primeiro_ramal["bus1"],
                "ramal_bus2": primeiro_ramal["bus2"],

                # Último bus1 encontrado subindo dentro de RamaisBT
                "primeiro_bus1_ramais": primeiro_bus1_ramais,
                "qtd_ramais_percorridos": len(caminho_ramais),

                # SegmentosBT
                "segmento_bus1_direto": segmento_bus1_direto,
                "primeiro_bus1_segmento": primeiro_bus1_segmento or "",
                "qtd_segmentos_percorridos": len(caminho_segmentos),
                "status": status,
            }
        )

    return resultados


def salvar_resultado_csv(
    resultados: list[dict],
    arquivo_saida: Path,
) -> None:
    """
    Salva o resultado em CSV.
    """
    arquivo_saida.parent.mkdir(parents=True, exist_ok=True)

    colunas = [
        "nome_load",
        "ramal",
        "bus_carga",
        "ramal_bus1",
        "ramal_bus2",
        "primeiro_bus1_ramais",
        "qtd_ramais_percorridos",
        "segmento_bus1_direto",
        "primeiro_bus1_segmento",
        "qtd_segmentos_percorridos",
        "status",
    ]

    with open(arquivo_saida, "w", encoding="utf-8-sig", newline="") as arquivo:
        writer = csv.DictWriter(
            arquivo,
            fieldnames=colunas,
            delimiter=";",
        )

        writer.writeheader()

        for item in resultados:
            writer.writerow(item)


def executar_search_segbt() -> None:
    """
    Executa a busca do primeiro bus1 do SegmentosBT para as cargas EV.
    """
    resultados = buscar_segbt_para_cargas_ev(
        arquivo_cargas_ev=ARQUIVO_CARGAS_EV,
        arquivo_ramais_bt=ARQUIVO_RAMAIS_BT,
        arquivo_segmentos_bt=ARQUIVO_SEGMENTOS_BT,
    )

    if not resultados:
        print("Nenhum resultado encontrado.")
        return

    salvar_resultado_csv(
        resultados=resultados,
        arquivo_saida=ARQUIVO_SAIDA,
    )


    print(f"Total de cargas EV analisadas: {len(resultados)}")

    total_ok = sum(1 for item in resultados if item["status"] == "OK")
    total_ramal_nao_encontrado = sum(
        1 for item in resultados if item["status"] == "RAMAL_NAO_ENCONTRADO"
    )
    total_segmento_nao_encontrado = sum(
        1 for item in resultados if item["status"] == "SEGMENTO_NAO_ENCONTRADO"
    )

    print(f"Total OK: {total_ok}")
    print(f"Ramal não encontrado: {total_ramal_nao_encontrado}")
    print(f"Segmento não encontrado: {total_segmento_nao_encontrado}")

    print("\nTodos os resultados:")
    for item in resultados:
        print(
            f'{item["nome_load"]} | '
            f'ramal={item["ramal"]} | '
            f'bus carga={item["bus_carga"]} | '
            f'ramal bus1={item["ramal_bus1"]} | '
            f'ramal bus2={item["ramal_bus2"]} | '
            f'primeiro bus1 RamaisBT={item["primeiro_bus1_ramais"]} | '
            f'ramais percorridos={item["qtd_ramais_percorridos"]} | '
            f'primeiro bus1 SegmentoBT={item["primeiro_bus1_segmento"]} | '
            f'segmentos percorridos={item["qtd_segmentos_percorridos"]} | '
            f'status={item["status"]}'
        )


if __name__ == "__main__":
    executar_search_segbt()