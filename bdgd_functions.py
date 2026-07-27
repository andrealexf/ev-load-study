from pathlib import Path
import json

import pandas as pd
import pyogrio


def localizar_camada(gdb_path: Path, nome_camada: str) -> str:
    layers_info = pyogrio.list_layers(gdb_path)
    layers = [linha[0] for linha in layers_info]

    for layer in layers:
        if layer.upper() == nome_camada.upper():
            return layer

    raise ValueError(
        f"Camada {nome_camada} não encontrada no GDB.\n"
        f"Camadas disponíveis:\n{layers}"
    )


def normalizar_texto(valor) -> str:
    if pd.isna(valor):
        return ""

    return str(valor).strip().upper()


def normalizar_codigo(valor) -> str:
    if pd.isna(valor):
        return ""

    texto = str(valor).strip()

    if texto.endswith(".0"):
        texto = texto[:-2]

    texto = texto.replace(" ", "")

    return texto


def escapar_sql_texto(valor: str) -> str:
    return str(valor).replace("'", "''")


def ler_ucbt_filtrada_por_ctmt(
    gdb_path: Path,
    camada_ucbt: str,
    ctmt_filtro: str,
) -> pd.DataFrame:
    camada = localizar_camada(gdb_path, camada_ucbt)

    ctmt_sql = escapar_sql_texto(ctmt_filtro)

    where = f"CTMT = '{ctmt_sql}'"

    print(f"Filtro aplicado no GDB: {where}")

    df = pyogrio.read_dataframe(
        gdb_path,
        layer=camada,
        read_geometry=False,
        where=where,
        columns=[
            "BRR",
            "PAC",
            "RAMAL",
            "CTMT",
            "CLAS_SUB",
        ],
    )

    return df


def aplicar_filtro_clas_sub(
    df: pd.DataFrame,
    clas_sub_prefixo: str | None,
    ctmt_filtro: str,
) -> pd.DataFrame:
    if not clas_sub_prefixo:
        return df

    prefixo = str(clas_sub_prefixo).strip().upper()

    df = df[df["CLAS_SUB"].str.startswith(prefixo)]

    if df.empty:
        print(
            f"Nenhum registro encontrado com CTMT = {ctmt_filtro} "
            f"e CLAS_SUB começando com {clas_sub_prefixo}"
        )

    return df


def preparar_dataframe_ucbt(
    df: pd.DataFrame,
    clas_sub_prefixo: str | None,
    ctmt_filtro: str,
) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.copy()

    df["BRR"] = df["BRR"].apply(normalizar_texto)
    df["CLAS_SUB"] = df["CLAS_SUB"].apply(normalizar_texto)
    df["PAC"] = df["PAC"].apply(normalizar_codigo)
    df["RAMAL"] = df["RAMAL"].apply(normalizar_codigo)

    df = df[df["BRR"] != ""]

    if df.empty:
        print("Nenhum bairro válido encontrado na coluna BRR.")
        return df

    df = aplicar_filtro_clas_sub(
        df=df,
        clas_sub_prefixo=clas_sub_prefixo,
        ctmt_filtro=ctmt_filtro,
    )

    if df.empty:
        return df

    df = df[df["PAC"] != ""]

    if df.empty:
        print("Nenhum PAC válido encontrado.")
        return df

    df = df[df["RAMAL"] != ""]

    if df.empty:
        print("Nenhum RAMAL válido encontrado.")
        return df

    return df


def imprimir_coluna_ramal(df: pd.DataFrame) -> None:
    print("\nPrimeiros valores da coluna RAMAL:")
    print(
        df["RAMAL"]
        .dropna()
        .astype(str)
        .str.strip()
        .drop_duplicates()
        .sort_values()
        .head(50)
        .to_string(index=False)
    )


def gerar_dicionario_bairro_pacs(df: pd.DataFrame) -> dict:
    resultado = {}

    for bairro, grupo in df.groupby("BRR"):
        pacs = (
            grupo["PAC"]
            .dropna()
            .astype(str)
            .str.strip()
            .drop_duplicates()
            .sort_values()
            .tolist()
        )

        resultado[bairro] = pacs

    return dict(sorted(resultado.items()))


def salvar_json(resultado: dict, arquivo_json: Path | None = None) -> None:
    """
    Salva o resultado em arquivo JSON.
    Se arquivo_json for None, não gera o arquivo.
    """
    if arquivo_json is None:
        return

    arquivo_json.parent.mkdir(parents=True, exist_ok=True)

    with open(arquivo_json, "w", encoding="utf-8") as arquivo:
        json.dump(
            resultado,
            arquivo,
            ensure_ascii=False,
            indent=4,
        )

def gerar_linhas_loads_dss(df: pd.DataFrame) -> list[str]:
    linhas = []

    df_loads = df[
        [
            "RAMAL",
            "PAC",
        ]
    ].drop_duplicates()


    for _, row in df_loads.iterrows():
        ramal = str(row["RAMAL"]).strip()
        pac = str(row["PAC"]).strip()

        if not ramal or not pac:
            continue

        linha = f'{ramal};{pac}'
        linhas.append(linha)

    return linhas


def salvar_loads_dss(
    df: pd.DataFrame,
    arquivo_loads_dss: Path,
) -> None:
    arquivo_loads_dss.parent.mkdir(parents=True, exist_ok=True)

    linhas = gerar_linhas_loads_dss(df)

    with open(arquivo_loads_dss, "w", encoding="utf-8") as arquivo:
        for linha in linhas:
            arquivo.write(linha + "\n")

    print(f"Total de linhas Load geradas: {len(linhas)}")


def gerar_json_brr_pac_por_bairro(
    gdb_path: Path,
    arquivo_loads_dss: Path,
    camada_ucbt: str,
    ctmt_filtro: str,
    clas_sub_prefixo: str | None = None,
    arquivo_json: Path | None = None,
) -> None:
    if not gdb_path.exists():
        raise FileNotFoundError(f"GDB não encontrado: {gdb_path}")

    print("=" * 80)
    print("Gerando JSON BRR x PAC da UCBT_tab")
    print("=" * 80)
    print(f"GDB: {gdb_path}")
    print(f"Camada: {camada_ucbt}")
    print(f"Filtro CTMT: {ctmt_filtro}")
    print(f"Filtro CLAS_SUB_PREFIXO: {clas_sub_prefixo}")

    if arquivo_json:
        print(f"Arquivo JSON: {arquivo_json}")
    else:
        print("Arquivo JSON: não será gerado")

    print(f"Arquivo Loads DSS: {arquivo_loads_dss}")
    print("=" * 80)

    df = ler_ucbt_filtrada_por_ctmt(
        gdb_path=gdb_path,
        camada_ucbt=camada_ucbt,
        ctmt_filtro=ctmt_filtro,
    )

    if df.empty:
        print(f"Nenhum registro encontrado com CTMT = {ctmt_filtro}")
        return

    print(f"Total de registros lidos com CTMT = {ctmt_filtro}: {len(df)}")

    df = preparar_dataframe_ucbt(
        df=df,
        clas_sub_prefixo=clas_sub_prefixo,
        ctmt_filtro=ctmt_filtro,
    )

    if df.empty:
        return

    if clas_sub_prefixo:
        print(
            f"Total após filtro CLAS_SUB começando com "
            f"{clas_sub_prefixo}: {len(df)}"
        )

    imprimir_coluna_ramal(df)

    resultado = gerar_dicionario_bairro_pacs(df)

    if arquivo_json is not None:
        salvar_json(
            resultado=resultado,
            arquivo_json=arquivo_json,
        )

    salvar_loads_dss(
        df=df,
        arquivo_loads_dss=arquivo_loads_dss,
    )

    print("\nExemplo dos primeiros bairros no JSON:")
    exemplo = dict(list(resultado.items())[:5])
    print(json.dumps(exemplo, ensure_ascii=False, indent=4))

    print("\nExemplo das primeiras linhas Load:")
    for linha in gerar_linhas_loads_dss(df)[:10]:
        print(linha)

    print("\n" + "=" * 80)
    print(f"Total de bairros no JSON: {len(resultado)}")
    if arquivo_json:
        print(f"Arquivo JSON gerado: {arquivo_json.resolve()}")
    print(f"Arquivo Loads DSS gerado: {arquivo_loads_dss.resolve()}")
    print("=" * 80)