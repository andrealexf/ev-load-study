from pathlib import Path
import csv


DIRETORIO_CODIGO = Path(__file__).resolve().parent

ARQUIVO_ENTRADA = DIRETORIO_CODIGO / "resultado_search_segbt.csv"

ARQUIVO_SAIDA = DIRETORIO_CODIGO / "BusMarkers_EV.dss"


def normalizar_texto(valor) -> str:
    if valor is None:
        return ""

    return str(valor).strip()


def identificar_tipo_carga(
    nome_load: str,
) -> str:
    nome = normalizar_texto(nome_load).upper()

    if nome.startswith("TW_"):
        return "TW"

    if nome.startswith("TWO_WHEELER_"):
        return "TW"

    if nome.startswith("TWO_WHEELERS_"):
        return "TW"

    if nome.startswith("LDV_"):
        return "LDV"

    if nome.startswith("EV_"):
        return "LDV"

    return "LDV"


def obter_cor_bus_marker(
    tipo_carga: str,
) -> str:
    tipo = normalizar_texto(tipo_carga).upper()

    if tipo == "TW":
        return "Blue"

    return "Red"


def ler_bus_markers(
    arquivo_entrada: Path,
) -> list[dict]:
    if not arquivo_entrada.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {arquivo_entrada}")

    markers = []

    with open(arquivo_entrada, "r", encoding="utf-8-sig", newline="") as arquivo:
        leitor = csv.DictReader(
            arquivo,
            delimiter=";",
        )

        if not leitor.fieldnames:
            raise ValueError("Arquivo CSV sem cabeçalho.")

        colunas_obrigatorias = [
            "nome_load",
            "primeiro_bus1_segmento",
        ]

        for coluna in colunas_obrigatorias:
            if coluna not in leitor.fieldnames:
                raise ValueError(
                    f"Coluna '{coluna}' não encontrada no CSV. "
                    f"Colunas disponíveis: {leitor.fieldnames}"
                )

        for linha in leitor:
            bus = normalizar_texto(
                linha.get("primeiro_bus1_segmento")
            )

            if not bus:
                continue

            nome_load = normalizar_texto(
                linha.get("nome_load")
            )

            tipo_carga = identificar_tipo_carga(
                nome_load=nome_load,
            )

            cor = obter_cor_bus_marker(
                tipo_carga=tipo_carga,
            )

            markers.append(
                {
                    "bus": bus,
                    "nome_load": nome_load,
                    "tipo_carga": tipo_carga,
                    "cor": cor,
                }
            )

    return markers


def gerar_linhas_bus_marker(
    markers: list[dict],
    remover_duplicados: bool = True,
) -> list[str]:
    linhas = []
    chaves_usadas = set()

    for marker in markers:
        bus = marker["bus"]
        cor = marker["cor"]
        tipo_carga = marker["tipo_carga"]

        if remover_duplicados:
            chave = (
                bus,
                cor,
            )

            if chave in chaves_usadas:
                continue

            chaves_usadas.add(chave)

        linha = (
            f'AddBusMarker Bus="{bus}" '
            f"code=15 "
            f"color={cor} "
            f"size=4 "
            f"! tipo={tipo_carga}"
        )

        linhas.append(linha)

    return linhas


def salvar_bus_markers(
    linhas: list[str],
    arquivo_saida: Path,
) -> None:
    arquivo_saida.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(arquivo_saida, "w", encoding="utf-8") as arquivo:
        for linha in linhas:
            arquivo.write(linha + "\n")


def executar_add_bus_marker() -> None:
    markers = ler_bus_markers(
        arquivo_entrada=ARQUIVO_ENTRADA,
    )

    if not markers:
        print("Nenhum primeiro_bus1_segmento encontrado para gerar BusMarker.")
        return

    linhas = gerar_linhas_bus_marker(
        markers=markers,
        remover_duplicados=True,
    )

    salvar_bus_markers(
        linhas=linhas,
        arquivo_saida=ARQUIVO_SAIDA,
    )

    total_ldv = sum(
        1
        for marker in markers
        if marker["tipo_carga"] == "LDV"
    )

    total_tw = sum(
        1
        for marker in markers
        if marker["tipo_carga"] == "TW"
    )

    print("=" * 80)
    print("Arquivo BusMarkers gerado")
    print("=" * 80)
    print(f"Arquivo entrada: {ARQUIVO_ENTRADA}")
    print(f"Arquivo saída: {ARQUIVO_SAIDA}")
    print(f"Total de markers encontrados: {len(markers)}")
    print(f"Total LDV encontrados: {total_ldv}")
    print(f"Total TW encontrados: {total_tw}")
    print(f"Total de BusMarkers gerados: {len(linhas)}")

    print("\nPrimeiras linhas geradas:")
    for linha in linhas[:10]:
        print(linha)

    print("=" * 80)


if __name__ == "__main__":
    executar_add_bus_marker()