from pathlib import Path
import csv
import io


colunas_obrigatorias = {
    "hora_dia": "Hora_dia",
    "trucks": "trucks",
    "tw": "tw",
    "ldv": "ldv",
    "bus": "bus",
}


def localizar_arquivo_numero_veiculos(
    diretorio_codigo: Path,
    nivel_eletrificacao: int,
) -> Path:
    diretorio_numero_veiculos = Path(diretorio_codigo) / "numero veiculos"
    diretorio_nivel = (
        diretorio_numero_veiculos
        / f"{nivel_eletrificacao}% de eletrificação"
    )

    if not diretorio_nivel.exists():
        raise FileNotFoundError(
            f"Diretório do cenário de {nivel_eletrificacao}% não encontrado:\n"
            f"{diretorio_nivel}"
        )

    nome_base = f"numEV_DU_{nivel_eletrificacao}"
    arquivo_exato = diretorio_nivel / f"{nome_base}.csv"

    if arquivo_exato.exists():
        return arquivo_exato

    candidatos = sorted(
        arquivo
        for arquivo in diretorio_nivel.glob(f"{nome_base}*")
        if arquivo.is_file()
    )

    if len(candidatos) == 1:
        return candidatos[0]

    if not candidatos:
        raise FileNotFoundError(
            f"Arquivo {nome_base}.csv não encontrado em:\n"
            f"{diretorio_nivel}"
        )

    nomes = "\n".join(f"- {arquivo.name}" for arquivo in candidatos)
    raise ValueError(
        f"Mais de um arquivo compatível com {nome_base} foi encontrado:\n"
        f"{nomes}"
    )


def detectar_delimitador_csv(texto: str) -> str:
    linhas = [linha for linha in texto.splitlines() if linha.strip()]

    if not linhas:
        raise ValueError("O arquivo CSV está vazio.")

    cabecalho = linhas[0]

    for delimitador in (";", ",", "\t"):
        if delimitador in cabecalho:
            return delimitador

    try:
        return csv.Sniffer().sniff(texto[:4096]).delimiter
    except csv.Error as exc:
        raise ValueError(
            "Não foi possível identificar o delimitador do arquivo CSV."
        ) from exc


def converter_numero(valor: str, campo: str, arquivo: Path) -> float:
    texto = str(valor).strip().replace(" ", "")

    if not texto:
        raise ValueError(
            f"Valor vazio para a coluna {campo} em {arquivo}."
        )

    if "," in texto and "." not in texto:
        texto = texto.replace(",", ".")

    try:
        return float(texto)
    except ValueError as exc:
        raise ValueError(
            f"Valor inválido para a coluna {campo} em {arquivo}: {valor}"
        ) from exc


def converter_quantidade(valor: str, campo: str, arquivo: Path) -> int:
    numero = converter_numero(valor=valor, campo=campo, arquivo=arquivo)

    if not numero.is_integer():
        raise ValueError(
            f"A quantidade da coluna {campo} deve ser inteira em {arquivo}: "
            f"{valor}"
        )

    quantidade = int(numero)

    if quantidade < 0:
        raise ValueError(
            f"A quantidade da coluna {campo} não pode ser negativa em "
            f"{arquivo}: {valor}"
        )

    return quantidade


def carregar_numero_veiculos_nivel(
    diretorio_codigo: Path,
    nivel_eletrificacao: int,
    hora_simulacao: float,
) -> dict:
    arquivo = localizar_arquivo_numero_veiculos(
        diretorio_codigo=diretorio_codigo,
        nivel_eletrificacao=nivel_eletrificacao,
    )

    try:
        texto = arquivo.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        texto = arquivo.read_text(encoding="cp1252")

    delimitador = detectar_delimitador_csv(texto=texto,)
    reader = csv.DictReader(io.StringIO(texto), delimiter=delimitador)

    if not reader.fieldnames:
        raise ValueError(f"Cabeçalho não encontrado em {arquivo}.")

    mapa_colunas = {
        coluna.strip().lower(): coluna
        for coluna in reader.fieldnames
        if coluna is not None
    }

    faltantes = [
        nome_original
        for chave, nome_original in colunas_obrigatorias.items()
        if chave not in mapa_colunas
    ]

    if faltantes:
        raise ValueError(
            f"Colunas obrigatórias ausentes em {arquivo}: "
            f"{', '.join(faltantes)}"
        )

    horas_disponiveis = []

    for linha in reader:
        hora_arquivo = converter_numero(
            valor=linha[mapa_colunas["hora_dia"]],
            campo="Hora_dia",
            arquivo=arquivo,
        )
        horas_disponiveis.append(hora_arquivo)

        if abs(hora_arquivo - float(hora_simulacao)) > 1e-9:
            continue

        return {
            "nivel_eletrificacao": int(nivel_eletrificacao),
            "hora_simulacao": hora_arquivo,
            "quantidade_trucks": converter_quantidade(
                valor=linha[mapa_colunas["trucks"]],
                campo="trucks",
                arquivo=arquivo,
            ),
            "quantidade_two_wheelers": converter_quantidade(
                valor=linha[mapa_colunas["tw"]],
                campo="tw",
                arquivo=arquivo,
            ),
            "quantidade_ldv": converter_quantidade(
                valor=linha[mapa_colunas["ldv"]],
                campo="ldv",
                arquivo=arquivo,
            ),
            "quantidade_buses": converter_quantidade(
                valor=linha[mapa_colunas["bus"]],
                campo="bus",
                arquivo=arquivo,
            ),
            "arquivo_origem": arquivo,
        }

    horas_formatadas = ", ".join(
        f"{hora:g}"
        for hora in horas_disponiveis
    )
    raise ValueError(
        f"Hora {float(hora_simulacao):g} não encontrada em {arquivo}. "
        f"Horas disponíveis: {horas_formatadas}"
    )


def carregar_cenarios_eletrificacao(
    diretorio_codigo: Path,
    niveis_eletrificacao: list[int],
    hora_simulacao: float,
) -> list[dict]:
    if not niveis_eletrificacao:
        raise ValueError("Informe ao menos um nível de eletrificação.")

    cenarios = []

    for nivel_eletrificacao in niveis_eletrificacao:
        cenarios.append(
            carregar_numero_veiculos_nivel(
                diretorio_codigo=diretorio_codigo,
                nivel_eletrificacao=int(nivel_eletrificacao),
                hora_simulacao=hora_simulacao,
            )
        )

    return cenarios
