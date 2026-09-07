from pathlib import Path
from collections import defaultdict
import csv
import random
import re


ALIMENTADORES = [
    "IJAU05",
    "IJAU06",
    "IJAU07",
    "IJAU10",
    "IJAU11",
    "IJAU13",
    "IJAU14",
    "IJAU15",
]


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
    match = re.search(r'"Load\.([^"]+)"', linha, flags=re.IGNORECASE)
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


def obter_parametro_linha(linha: str, parametro: str, valor_padrao: str | None = None) -> str:
    match = re.search(rf'{parametro}="([^"]+)"', linha, flags=re.IGNORECASE)
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
    vistos = set()
    for arquivo in arquivos_encontrados:
        caminho = arquivo.resolve()
        if caminho in vistos:
            continue
        vistos.add(caminho)
        arquivos_unicos.append(arquivo)
    if not arquivos_unicos:
        raise FileNotFoundError(
            f"CargasBT não encontrado para {alimentador}.\n"
            f"Diretório verificado:\n{diretorio_dss_base}"
        )
    return arquivos_unicos[0]


def localizar_arquivo_ucbt(diretorio_bdgd: Path, alimentador: str) -> Path:
    arquivo = Path(diretorio_bdgd) / f"Loads_UCBT_{alimentador}.txt"
    if not arquivo.exists():
        raise FileNotFoundError(f"Arquivo UCBT não encontrado:\n{arquivo}")
    return arquivo


def ler_ucbts_alimentador(arquivo_ucbt: Path, alimentador: str) -> list[dict]:
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


def carregar_pool_global(diretorio_dss_base: Path, diretorio_bdgd: Path) -> tuple[list[dict], list[dict]]:
    pool_valido = []
    pool_invalido = []
    indice_por_chave_global = defaultdict(int)
    for alimentador in ALIMENTADORES:
        arquivo_ucbt = localizar_arquivo_ucbt(diretorio_bdgd, alimentador)
        arquivo_cargas = localizar_arquivo_cargas_bt(diretorio_dss_base, alimentador)
        ucbts = ler_ucbts_alimentador(arquivo_ucbt, alimentador)
        cargas = ler_cargas_dss(arquivo_cargas)
        for ucbt in ucbts:
            chave = (ucbt["ramal"], ucbt["pac"])
            linhas = cargas.get(chave, [])
            if not linhas:
                pool_invalido.append(ucbt)
                continue
            chave_global = (alimentador, ucbt["ramal"], ucbt["pac"])
            indice = indice_por_chave_global[chave_global]
            linha_original = linhas[indice % len(linhas)]
            indice_por_chave_global[chave_global] += 1
            ucbt_valida = ucbt.copy()
            ucbt_valida["linha_original"] = linha_original
            ucbt_valida["arquivo_cargas_bt"] = arquivo_cargas
            pool_valido.append(ucbt_valida)
    return pool_valido, pool_invalido


def selecionar_ucbts_globalmente(
    pool_valido: list[dict],
    quantidade_ldv: int,
    quantidade_two_wheelers: int,
    seed: int,
) -> tuple[list[dict], list[dict]]:
    quantidade_total = quantidade_ldv + quantidade_two_wheelers
    if quantidade_total <= 0:
        raise ValueError("A quantidade total de EVs precisa ser maior que zero.")
    if quantidade_total > len(pool_valido):
        raise ValueError(
            f"Foram solicitados {quantidade_total} EVs, mas existem apenas "
            f"{len(pool_valido)} UCBTs válidas no pool global."
        )
    sorteador = random.Random(seed)
    selecionadas = sorteador.sample(pool_valido, quantidade_total)
    return selecionadas[:quantidade_ldv], selecionadas[quantidade_ldv:]


def montar_linha_ev(ucbt: dict, tipo: str) -> str:
    linha_original = ucbt["linha_original"]
    nome_original = extrair_nome_carga(linha_original)
    if not nome_original:
        raise ValueError(f"Nome da carga não encontrado:\n{linha_original}")
    bus1 = obter_parametro_linha(linha_original, "bus1")
    conn = obter_parametro_linha(linha_original, "conn", "wye")
    kv = obter_parametro_linha(linha_original, "kv")
    phases = 3 if bus1.endswith(".1.2.3.4") else 1
    if tipo == "LDV":
        prefixo = "LDV"
        kw = 3.5
    elif tipo == "TW":
        prefixo = "TW"
        kw = 2.0
    else:
        raise ValueError(f"Tipo inválido: {tipo}")
    nome_ev = f"{prefixo}_{nome_original}_{ucbt['ctmt']}_{ucbt['pac']}_{ucbt['id_ucbt']:06d}"
    return (
        f'New "Load.{nome_ev}" '
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
    )


def gerar_arquivos_por_alimentador(
    ldvs: list[dict],
    tws: list[dict],
    diretorio_saida: Path,
    numero_simulacao: int,
    seed: int,
) -> dict[str, Path]:
    cargas_por_ctmt = defaultdict(list)
    for ucbt in ldvs:
        cargas_por_ctmt[ucbt["ctmt"]].append(montar_linha_ev(ucbt, "LDV"))
    for ucbt in tws:
        cargas_por_ctmt[ucbt["ctmt"]].append(montar_linha_ev(ucbt, "TW"))
    arquivos = {}
    for ctmt, linhas in cargas_por_ctmt.items():
        arquivo_saida = (
            Path(diretorio_saida)
            / f"Cargas_EV_{ctmt}_Sim_{numero_simulacao:05d}_{seed}.dss"
        )
        arquivo_saida.parent.mkdir(parents=True, exist_ok=True)
        with open(arquivo_saida, "w", encoding="utf-8") as arquivo:
            for linha in linhas:
                arquivo.write(linha + "\n")
        arquivos[ctmt] = arquivo_saida
    return arquivos


def executar_add_ev(
    quantidade_ldv: int,
    quantidade_two_wheelers: int,
    diretorio_dss_base: Path,
    diretorio_bdgd: Path,
    diretorio_saida: Path,
    numero_simulacao: int,
    seed: int,
) -> dict:
    pool_valido, pool_invalido = carregar_pool_global(
        diretorio_dss_base=diretorio_dss_base,
        diretorio_bdgd=diretorio_bdgd,
    )
    ldvs, tws = selecionar_ucbts_globalmente(
        pool_valido=pool_valido,
        quantidade_ldv=quantidade_ldv,
        quantidade_two_wheelers=quantidade_two_wheelers,
        seed=seed,
    )
    arquivos = gerar_arquivos_por_alimentador(
        ldvs=ldvs,
        tws=tws,
        diretorio_saida=diretorio_saida,
        numero_simulacao=numero_simulacao,
        seed=seed,
    )
    return {
        "seed": seed,
        "ldvs": ldvs,
        "tws": tws,
        "arquivos_por_alimentador": arquivos,
        "total_pool_valido": len(pool_valido),
        "total_pool_invalido": len(pool_invalido),
    }