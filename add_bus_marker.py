from pathlib import Path
import csv


DIRETORIO_CODIGO = Path(__file__).resolve().parent

ARQUIVO_ENTRADA = DIRETORIO_CODIGO / "resultado_search_segbt.csv"

ARQUIVO_SAIDA = DIRETORIO_CODIGO / "BusMarkers_EV.dss"


def normalizar_bus(valor) -> str:

    if valor is None:
        return ""

    return str(valor).strip()


def ler_primeiros_bus1_segmento(
    arquivo_entrada: Path,
) -> list[str]:

    if not arquivo_entrada.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {arquivo_entrada}")

    buses = []

    with open(arquivo_entrada, "r", encoding="utf-8-sig", newline="") as arquivo:
        leitor = csv.DictReader(
            arquivo,
            delimiter=";",
        )

        if not leitor.fieldnames:
            raise ValueError("Arquivo CSV sem cabeçalho.")

        if "primeiro_bus1_segmento" not in leitor.fieldnames:
            raise ValueError(
                "Coluna 'primeiro_bus1_segmento' não encontrada no CSV. "
                f"Colunas disponíveis: {leitor.fieldnames}"
            )

        for linha in leitor:
            bus = normalizar_bus(linha.get("primeiro_bus1_segmento"))

            if not bus:
                continue

            buses.append(bus)

    return buses


def gerar_linhas_bus_marker(
    buses: list[str],
    remover_duplicados: bool = True,
) -> list[str]:

    linhas = []
    buses_usados = set()

    for bus in buses:
        if remover_duplicados:
            if bus in buses_usados:
                continue

            buses_usados.add(bus)

        linha = f'AddBusMarker Bus="{bus}" code=15 color=Red size=4'

        linhas.append(linha)

    return linhas


def salvar_bus_markers(
    linhas: list[str],
    arquivo_saida: Path,
) -> None:

    arquivo_saida.parent.mkdir(parents=True, exist_ok=True)

    with open(arquivo_saida, "w", encoding="utf-8") as arquivo:
        for linha in linhas:
            arquivo.write(linha + "\n")


def executar_add_bus_marker() -> None:

    buses = ler_primeiros_bus1_segmento(
        arquivo_entrada=ARQUIVO_ENTRADA,
    )

    if not buses:
        print("Nenhum primeiro_bus1_segmento encontrado para gerar BusMarker.")
        return

    linhas = gerar_linhas_bus_marker(
        buses=buses,
        remover_duplicados=True,
    )

    salvar_bus_markers(
        linhas=linhas,
        arquivo_saida=ARQUIVO_SAIDA,
    )

    print("")
    print("Arquivo BusMarkers gerado")
    print("")
    #print(f"Arquivo entrada: {ARQUIVO_ENTRADA}")
    print(f"Arquivo saída: {ARQUIVO_SAIDA}")
    print(f"Total de buses encontrados: {len(buses)}")
    print(f"Total de BusMarkers gerados: {len(linhas)}")

    print("\nPrimeiras linhas geradas:")
    for linha in linhas[:10]:
        print(linha)

    print("")


if __name__ == "__main__":
    executar_add_bus_marker()