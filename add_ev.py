from pathlib import Path
from collections import defaultdict
import csv
import random
import re


alimentadores = [
    "IJAU05",
    "IJAU06",
    "IJAU07",
    "IJAU10",
    "IJAU11",
    "IJAU13",
    "IJAU14",
    "IJAU15",
]

potencia_ldv_kw = 3.5
potencia_two_wheeler_kw = 2.0
potencia_truck_kw = 50.0

cache_cargas_dss = {}
cache_ucbts = {}
cache_pool_global = {}


def normalizar_codigo(valor) -> str:
    if valor is None:
        return ""

    texto = str(valor).strip()

    if texto.endswith(".0"):
        texto = texto[:-2]

    return texto.replace(" ", "")


def normalizar_ctmt(valor) -> str:
    return str(valor or "").strip().upper()


def extrair_nome_carga(linha: str) -> str | None:
    match = re.search(r'"Load\.([^\"]+)"', linha, flags=re.IGNORECASE)

    if not match:
        return None

    return match.group(1)


def extrair_carga_base(nome_carga: str) -> str:
    return re.sub(r"_M\d+$", "", nome_carga, flags=re.IGNORECASE)


def extrair_ramal_da_carga_base(carga_base: str) -> str:
    texto = str(carga_base).strip()

    if texto.upper().startswith("BT_"):
        texto = texto[3:]

    texto = re.sub(r"_\d+$", "", texto)

    return normalizar_codigo(texto)


def obter_parametro_linha(
    linha: str,
    parametro: str,
    valor_padrao: str | None = None,
) -> str:
    match = re.search(rf'{parametro}="([^\"]+)"', linha, flags=re.IGNORECASE)

    if match:
        return match.group(1)

    match = re.search(rf"{parametro}=([^\s]+)", linha, flags=re.IGNORECASE)

    if match:
        return match.group(1)

    if valor_padrao is not None:
        return valor_padrao

    raise ValueError(f"Parâmetro '{parametro}' não encontrado na linha:\n{linha}")


def extrair_pac_da_carga(linha: str) -> str:
    bus1 = obter_parametro_linha(linha, "bus1")
    return normalizar_codigo(bus1.split(".")[0])


def localizar_arquivo_cargas_bt(diretorio_dss_base: Path, alimentador: str) -> Path:
    diretorio_dss_base = Path(diretorio_dss_base)
    alimentador = str(alimentador).strip().upper()

    padroes = [
        f"CargasBT_DU01_2022124950_{alimentador}_--MBS-1--T--.dss",
        f"CargasBT_*_{alimentador}_*.dss",
        f"CargasBT_*{alimentador}*.dss",
    ]

    arquivos_encontrados = []

    for padrao in padroes:
        arquivos_encontrados.extend(sorted(diretorio_dss_base.glob(padrao)))

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
            f"CargasBT não encontrado para {alimentador}.\n"
            f"Diretório verificado:\n{diretorio_dss_base}"
        )

    return arquivos_unicos[0]


def localizar_arquivo_ucbt(
    diretorio_bdgd: Path,
    alimentador: str,
    classe_ucbt: str,
) -> Path:
    arquivo = Path(diretorio_bdgd) / f"Loads_UCBT_{classe_ucbt}_{alimentador}.txt"

    if not arquivo.exists():
        raise FileNotFoundError(f"Arquivo UCBT não encontrado:\n{arquivo}")

    return arquivo


def ler_ucbts_alimentador(
    arquivo_ucbt: Path,
    alimentador: str,
) -> list[dict]:
    ucbts = []

    with open(arquivo_ucbt, "r", encoding="utf-8-sig", newline="") as arquivo:
        leitor = csv.DictReader(arquivo, delimiter=";")

        if not leitor.fieldnames:
            raise ValueError(f"Arquivo sem cabeçalho: {arquivo_ucbt}")

        numero_ucbt = 0

        for linha in leitor:
            ramal = normalizar_codigo(linha.get("RAMAL"))
            pac = normalizar_codigo(linha.get("PAC"))

            if not ramal or not pac:
                continue

            ctmt = normalizar_ctmt(linha.get("CTMT")) or alimentador
            numero_ucbt += 1

            ucbts.append(
                {
                    "id_ucbt": numero_ucbt,
                    "ctmt": ctmt,
                    "ramal": ramal,
                    "pac": pac,
                    "brr": str(linha.get("BRR", "")).strip(),
                    "clas_sub": str(linha.get("CLAS_SUB", "")).strip(),
                }
            )

    return ucbts


def ler_cargas_dss(arquivo_cargas: Path) -> dict:
    cargas = defaultdict(list)

    with open(arquivo_cargas, "r", encoding="utf-8", errors="ignore") as arquivo:
        for linha in arquivo:
            nome = extrair_nome_carga(linha)

            if not nome:
                continue

            carga_base = extrair_carga_base(nome)
            ramal = extrair_ramal_da_carga_base(carga_base)

            if not ramal:
                continue

            try:
                pac = extrair_pac_da_carga(linha)
            except Exception:
                continue

            cargas[(ramal, pac)].append(linha.strip())

    return dict(cargas)


def obter_cargas_dss_cache(arquivo_cargas: Path) -> dict:
    chave = str(Path(arquivo_cargas).resolve())

    if chave not in cache_cargas_dss:
        cache_cargas_dss[chave] = ler_cargas_dss(arquivo_cargas=arquivo_cargas,)

    return cache_cargas_dss[chave]


def obter_ucbts_cache(arquivo_ucbt: Path, alimentador: str) -> list[dict]:
    chave = (
        str(Path(arquivo_ucbt).resolve()),
        alimentador,
    )

    if chave not in cache_ucbts:
        cache_ucbts[chave] = ler_ucbts_alimentador(
            arquivo_ucbt=arquivo_ucbt,
            alimentador=alimentador,
        )

    return cache_ucbts[chave]


def carregar_pool_global(
    diretorio_dss_base: Path,
    diretorio_bdgd: Path,
    classe_ucbt: str,
) -> tuple[list[dict], list[dict]]:
    chave_pool = (
        str(Path(diretorio_dss_base).resolve()),
        str(Path(diretorio_bdgd).resolve()),
        classe_ucbt,
    )

    if chave_pool in cache_pool_global:
        return cache_pool_global[chave_pool]

    pool_valido = []
    pool_invalido = []
    indice_por_chave_global = defaultdict(int)

    for alimentador in alimentadores:
        arquivo_ucbt = localizar_arquivo_ucbt(
            diretorio_bdgd=diretorio_bdgd,
            alimentador=alimentador,
            classe_ucbt=classe_ucbt,
        )

        arquivo_cargas = localizar_arquivo_cargas_bt(
            diretorio_dss_base=diretorio_dss_base,
            alimentador=alimentador,
        )

        ucbts = obter_ucbts_cache(arquivo_ucbt=arquivo_ucbt, alimentador=alimentador,)
        cargas = obter_cargas_dss_cache(arquivo_cargas=arquivo_cargas,)

        for ucbt in ucbts:
            chave = (
                ucbt["ramal"],
                ucbt["pac"],
            )

            linhas = cargas.get(chave, [])

            if not linhas:
                pool_invalido.append(ucbt)
                continue

            chave_global = (
                classe_ucbt,
                alimentador,
                ucbt["ramal"],
                ucbt["pac"],
            )

            indice = indice_por_chave_global[chave_global]
            linha_original = linhas[indice % len(linhas)]
            indice_por_chave_global[chave_global] += 1

            ucbt_valida = ucbt.copy()
            ucbt_valida["classe_ucbt"] = classe_ucbt
            ucbt_valida["linha_original"] = linha_original
            ucbt_valida["arquivo_cargas_bt"] = arquivo_cargas
            pool_valido.append(ucbt_valida)

    cache_pool_global[chave_pool] = (
        pool_valido,
        pool_invalido,
    )

    return cache_pool_global[chave_pool]


def selecionar_ucbts_globalmente(
    pool_valido: list[dict],
    quantidade: int,
    seed: int,
) -> list[dict]:
    if quantidade <= 0:
        return []

    if quantidade > len(pool_valido):
        raise ValueError(
            f"Foram solicitadas {quantidade} cargas, mas existem apenas "
            f"{len(pool_valido)} UCBTs válidas no pool global."
        )

    sorteador = random.Random(seed)
    return sorteador.sample(pool_valido, quantidade)


def montar_linha_ev(ucbt: dict, tipo: str, seed: int) -> tuple[str, dict]:
    linha_original = ucbt["linha_original"]
    nome_original = extrair_nome_carga(linha_original)

    if not nome_original:
        raise ValueError(f"Nome da carga não encontrado:\n{linha_original}")

    bus1 = obter_parametro_linha(linha_original, "bus1")
    conn = obter_parametro_linha(linha_original, "conn", "wye")
    kv = obter_parametro_linha(linha_original, "kv")
    phases = obter_parametro_linha(linha_original, "phases", "1")

    if tipo == "LDV":
        prefixo = "LDV"
        kw = potencia_ldv_kw
    elif tipo == "TW":
        prefixo = "TW"
        kw = potencia_two_wheeler_kw
    elif tipo == "TRUCK":
        prefixo = "TRUCK"
        kw = potencia_truck_kw
    else:
        raise ValueError(f"Tipo inválido: {tipo}")

    nome_carga = (
        f"{prefixo}_S{seed}_"
        f"{nome_original}_"
        f"{ucbt['ctmt']}_"
        f"{ucbt['pac']}_"
        f"{ucbt['id_ucbt']:06d}"
    )

    nome_elemento = f"Load.{nome_carga}"

    linha = (
        f'New "{nome_elemento}" '
        f'bus1="{bus1}" '
        f"phases={phases} "
        f"conn={conn} "
        f"model=1 "
        f"kv={kv} "
        f"kw={kw} "
        f"pf=1 "
        f"status=variable "
        f"vmaxpu=1.5 "
        f"vminpu=0.92 "
        f"enabled=yes "
        # f'daily="EV_1" '
        f"! tipo={tipo} "
        f"kw_ativo={kw} "
        f"classe_ucbt={ucbt.get('classe_ucbt', '')} "
        f"ctmt={ucbt['ctmt']} "
        f"ramal={ucbt['ramal']} "
        f"pac={ucbt['pac']}"
    )

    configuracao = {
        "nome": nome_elemento,
        "kw_ativo": float(kw),
        "tipo": tipo,
    }

    return linha, configuracao


def gerar_arquivos_por_alimentador(
    ldvs: list[dict],
    tws: list[dict],
    trucks: list[dict],
    diretorio_saida: Path,
    numero_simulacao: int,
    seed: int,
) -> tuple[dict[str, Path], list[dict]]:
    cargas_por_ctmt = defaultdict(list)
    configuracoes_cargas = []

    for ucbt in ldvs:
        linha, configuracao = montar_linha_ev(ucbt=ucbt, tipo="LDV", seed=seed,)
        cargas_por_ctmt[ucbt["ctmt"]].append(linha)
        configuracoes_cargas.append(configuracao)

    for ucbt in tws:
        linha, configuracao = montar_linha_ev(ucbt=ucbt, tipo="TW", seed=seed,)
        cargas_por_ctmt[ucbt["ctmt"]].append(linha)
        configuracoes_cargas.append(configuracao)

    for ucbt in trucks:
        linha, configuracao = montar_linha_ev(ucbt=ucbt, tipo="TRUCK", seed=seed,)
        cargas_por_ctmt[ucbt["ctmt"]].append(linha)
        configuracoes_cargas.append(configuracao)

    arquivos = {}


    for ctmt, linhas in cargas_por_ctmt.items():
        '''
        arquivo_saida = (
            Path(diretorio_saida)
            / f"Cargas_EV_{ctmt}_Sim_{numero_simulacao:05d}_{seed}.dss"
        )

        arquivo_saida.parent.mkdir(parents=True, exist_ok=True)

        with open(arquivo_saida, "w", encoding="utf-8") as arquivo:
            for linha in linhas:
                arquivo.write(linha + "\n")
        
        arquivos[ctmt] = arquivo_saida
        '''
        arquivos[ctmt] = linhas


    return arquivos, configuracoes_cargas


def executar_add_ev(
    quantidade_ldv: int,
    quantidade_two_wheelers: int,
    diretorio_dss_base: Path,
    diretorio_bdgd: Path,
    diretorio_saida: Path,
    numero_simulacao: int,
    seed: int,
    quantidade_trucks: int = 0,
) -> dict:
    if quantidade_ldv < 0 or quantidade_two_wheelers < 0 or quantidade_trucks < 0:
        raise ValueError("As quantidades não podem ser negativas.")

    quantidade_residencial = quantidade_ldv + quantidade_two_wheelers
    quantidade_total = quantidade_residencial + quantidade_trucks

    if quantidade_total <= 0:
        raise ValueError("A quantidade total de veículos deve ser maior que zero.")

    pool_residencial_valido = []
    pool_residencial_invalido = []
    pool_industrial_valido = []
    pool_industrial_invalido = []

    if quantidade_residencial > 0:
        pool_residencial_valido, pool_residencial_invalido = carregar_pool_global(
            diretorio_dss_base=diretorio_dss_base,
            diretorio_bdgd=diretorio_bdgd,
            classe_ucbt="RE",
        )

    if quantidade_trucks > 0:
        pool_industrial_valido, pool_industrial_invalido = carregar_pool_global(
            diretorio_dss_base=diretorio_dss_base,
            diretorio_bdgd=diretorio_bdgd,
            classe_ucbt="IN",
        )

    selecionadas_residenciais = selecionar_ucbts_globalmente(
        pool_valido=pool_residencial_valido,
        quantidade=quantidade_residencial,
        seed=seed,
    )

    ldvs = selecionadas_residenciais[:quantidade_ldv]
    tws = selecionadas_residenciais[quantidade_ldv:]

    trucks = selecionar_ucbts_globalmente(
        pool_valido=pool_industrial_valido,
        quantidade=quantidade_trucks,
        seed=seed + 50000,
    )

    arquivos, configuracoes_cargas = gerar_arquivos_por_alimentador(
        ldvs=ldvs,
        tws=tws,
        trucks=trucks,
        diretorio_saida=diretorio_saida,
        numero_simulacao=numero_simulacao,
        seed=seed,
    )

    return {
        "seed": seed,
        "ldvs": ldvs,
        "tws": tws,
        "trucks": trucks,
        "nomes_cargas": [item["nome"] for item in configuracoes_cargas],
        "configuracoes_cargas": configuracoes_cargas,
        "arquivos_por_alimentador": arquivos,
        "total_pool_residencial_valido": len(pool_residencial_valido),
        "total_pool_residencial_invalido": len(pool_residencial_invalido),
        "total_pool_industrial_valido": len(pool_industrial_valido),
        "total_pool_industrial_invalido": len(pool_industrial_invalido),
        "total_pool_valido": len(pool_residencial_valido) + len(pool_industrial_valido),
        "total_pool_invalido": len(pool_residencial_invalido) + len(pool_industrial_invalido),
    }
