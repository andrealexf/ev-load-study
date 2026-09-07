from pathlib import Path
import json

import pandas as pd
import pyogrio


def localizar_camada(
    gdb_path: Path,
    nome_camada: str,
) -> str:
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


def tratar_pac(
    valor,
    garantir_10_digitos: bool = True,
) -> str:
    if pd.isna(valor):
        return ""

    pac = str(valor).strip()

    if pac.endswith(".0"):
        pac = pac[:-2]

    pac = pac.replace(" ", "")

    if len(pac) <= 3:
        return ""

    pac = pac[3:]

    pac = "".join(
        caractere
        for caractere in pac
        if caractere.isdigit()
    )

    if not pac:
        return ""

    if not garantir_10_digitos:
        return pac

    if len(pac) == 10:
        return pac

    if len(pac) == 7:
        return "100" + pac

    if len(pac) == 8:
        return "10" + pac

    if len(pac) == 9:
        return "1" + pac

    if len(pac) < 10:
        return pac.zfill(10)

    if len(pac) > 10:
        return pac[-10:]

    return pac


def escapar_sql_texto(valor: str) -> str:
    return str(valor).replace("'", "''")


def ler_ucbt_filtrada_por_ctmt(
    gdb_path: Path,
    camada_ucbt: str,
    ctmt_filtro: str,
) -> pd.DataFrame:
    camada = localizar_camada(
        gdb_path=gdb_path,
        nome_camada=camada_ucbt,
    )

    ctmt_sql = escapar_sql_texto(
        valor=ctmt_filtro,
    )

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


def preparar_dataframe_ucbt(
    df: pd.DataFrame,
    garantir_pac_10_digitos: bool = True,
) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.copy()

    df["BRR"] = df["BRR"].apply(normalizar_texto)
    df["CLAS_SUB"] = df["CLAS_SUB"].apply(normalizar_texto)
    df["CTMT"] = df["CTMT"].apply(normalizar_texto)
    df["RAMAL"] = df["RAMAL"].apply(normalizar_codigo)

    df["PAC"] = df["PAC"].apply(
        lambda valor: tratar_pac(
            valor=valor,
            garantir_10_digitos=garantir_pac_10_digitos,
        )
    )

    return df


def filtrar_ucbt_residenciais(
    df: pd.DataFrame,
    clas_sub_prefixo: str | None,
) -> pd.DataFrame:
    if df.empty:
        return df

    if not clas_sub_prefixo:
        return df.copy()

    prefixo = str(clas_sub_prefixo).strip().upper()

    return df[
        df["CLAS_SUB"].str.startswith(
            prefixo,
            na=False,
        )
    ].copy()


def diagnosticar_ucbt_residenciais(
    df_total_ctmt: pd.DataFrame,
    df_residencial: pd.DataFrame,
    clas_sub_prefixo: str | None,
) -> None:
    prefixo = clas_sub_prefixo or "SEM FILTRO"

    total_ctmt = len(df_total_ctmt)
    total_residencial = len(df_residencial)

    if df_residencial.empty:
        total_brr_vazio = 0
        total_pac_vazio = 0
        total_ramal_vazio = 0
        total_pac_ramal_validos = 0
        total_brr_pac_validos = 0
        total_ramais_unicos = 0
    else:
        total_brr_vazio = len(
            df_residencial[
                df_residencial["BRR"] == ""
            ]
        )

        total_pac_vazio = len(
            df_residencial[
                df_residencial["PAC"] == ""
            ]
        )

        total_ramal_vazio = len(
            df_residencial[
                df_residencial["RAMAL"] == ""
            ]
        )

        total_pac_ramal_validos = len(
            df_residencial[
                (df_residencial["PAC"] != "")
                & (df_residencial["RAMAL"] != "")
            ]
        )

        total_brr_pac_validos = len(
            df_residencial[
                (df_residencial["BRR"] != "")
                & (df_residencial["PAC"] != "")
            ]
        )

        total_ramais_unicos = (
            df_residencial["RAMAL"]
            .dropna()
            .astype(str)
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .nunique()
        )

    print("")
    print("=" * 80)
    print("DIAGNÓSTICO UCBT")
    print("=" * 80)
    print(f"Total lido do CTMT: {total_ctmt}")
    print(f"Filtro CLAS_SUB_PREFIXO: {prefixo}")
    print(f"Total após filtro CLAS_SUB: {total_residencial}")
    print(f"Residenciais com BRR vazio: {total_brr_vazio}")
    print(f"Residenciais com PAC vazio: {total_pac_vazio}")
    print(f"Residenciais com RAMAL vazio: {total_ramal_vazio}")
    print(f"Residenciais com PAC e RAMAL válidos: {total_pac_ramal_validos}")
    print(f"Residenciais com BRR e PAC válidos para JSON: {total_brr_pac_validos}")
    print(f"RAMAIS únicos entre residenciais: {total_ramais_unicos}")
    print("=" * 80)
    print("")


def separar_dataframe_para_json(
    df_residencial: pd.DataFrame,
) -> pd.DataFrame:
    if df_residencial.empty:
        return df_residencial.copy()

    df_json = df_residencial[
        (df_residencial["BRR"] != "")
        & (df_residencial["PAC"] != "")
    ].copy()

    return df_json


def separar_dataframe_para_ramais(
    df_residencial: pd.DataFrame,
) -> pd.DataFrame:
    if df_residencial.empty:
        return df_residencial.copy()

    df_ramais = df_residencial[
        (df_residencial["PAC"] != "")
        & (df_residencial["RAMAL"] != "")
    ].copy()

    return df_ramais


def gerar_dicionario_bairro_pacs(
    df_json: pd.DataFrame,
) -> dict:
    resultado = {}

    if df_json.empty:
        return resultado

    for bairro, grupo in df_json.groupby("BRR"):
        pacs = (
            grupo["PAC"]
            .dropna()
            .astype(str)
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .drop_duplicates()
            .sort_values()
            .tolist()
        )

        resultado[bairro] = pacs

    return dict(
        sorted(
            resultado.items()
        )
    )


def salvar_json(
    resultado: dict,
    arquivo_json: Path | None = None,
) -> None:
    if arquivo_json is None:
        return

    arquivo_json.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        arquivo_json,
        "w",
        encoding="utf-8",
    ) as arquivo:
        json.dump(
            resultado,
            arquivo,
            ensure_ascii=False,
            indent=4,
        )


def salvar_ramais_txt(
    df_ramais: pd.DataFrame,
    arquivo_saida: Path | None = None,
) -> None:
    if arquivo_saida is None:
        return

    arquivo_saida.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    colunas_saida = [
        "RAMAL",
        "PAC",
        "BRR",
        "CLAS_SUB",
        "CTMT",
    ]

    df_saida = df_ramais[
        colunas_saida
    ].copy()

    df_saida = df_saida.sort_values(
        by=[
            "RAMAL",
            "PAC",
        ]
    )

    with open(
        arquivo_saida,
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as arquivo:
        arquivo.write("RAMAL;PAC;BRR;CLAS_SUB;CTMT\n")

        for _, linha in df_saida.iterrows():
            arquivo.write(
                f'{linha["RAMAL"]};'
                f'{linha["PAC"]};'
                f'{linha["BRR"]};'
                f'{linha["CLAS_SUB"]};'
                f'{linha["CTMT"]}\n'
            )


def salvar_diagnostico_csv(
    df_residencial: pd.DataFrame,
    arquivo_saida: Path | None = None,
) -> None:
    if arquivo_saida is None:
        return

    arquivo_saida.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    df_diag = df_residencial.copy()

    df_diag["BRR_VAZIO"] = df_diag["BRR"] == ""
    df_diag["PAC_VAZIO"] = df_diag["PAC"] == ""
    df_diag["RAMAL_VAZIO"] = df_diag["RAMAL"] == ""
    df_diag["VALIDO_PARA_RAMAL"] = (
        (df_diag["PAC"] != "")
        & (df_diag["RAMAL"] != "")
    )
    df_diag["VALIDO_PARA_JSON"] = (
        (df_diag["BRR"] != "")
        & (df_diag["PAC"] != "")
    )

    colunas = [
        "CTMT",
        "CLAS_SUB",
        "BRR",
        "PAC",
        "RAMAL",
        "BRR_VAZIO",
        "PAC_VAZIO",
        "RAMAL_VAZIO",
        "VALIDO_PARA_RAMAL",
        "VALIDO_PARA_JSON",
    ]

    df_diag[colunas].to_csv(
        arquivo_saida,
        index=False,
        sep=";",
        encoding="utf-8-sig",
    )


def gerar_json_brr_pac_por_bairro(
    gdb_path: Path,
    arquivo_loads_dss: Path | None,
    camada_ucbt: str,
    ctmt_filtro: str,
    clas_sub_prefixo: str | None = None,
    arquivo_json: Path | None = None,
    garantir_pac_10_digitos: bool = True,
    arquivo_diagnostico_csv: Path | None = None,
) -> None:
    if not gdb_path.exists():
        raise FileNotFoundError(f"GDB não encontrado: {gdb_path}")

    print("=" * 80)
    print("Extração UCBT da BDGD")
    print("=" * 80)
    print(f"GDB: {gdb_path}")
    print(f"Camada: {camada_ucbt}")
    print(f"Filtro CTMT: {ctmt_filtro}")
    print(f"Filtro CLAS_SUB_PREFIXO: {clas_sub_prefixo}")
    print(f"Arquivo ramais/loads: {arquivo_loads_dss}")
    print(f"Arquivo JSON: {arquivo_json}")
    print(f"Arquivo diagnóstico: {arquivo_diagnostico_csv}")
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
        garantir_pac_10_digitos=garantir_pac_10_digitos,
    )

    df_residencial = filtrar_ucbt_residenciais(
        df=df,
        clas_sub_prefixo=clas_sub_prefixo,
    )

    if df_residencial.empty:
        print(
            f"Nenhum registro encontrado com CLAS_SUB começando com "
            f"{clas_sub_prefixo}"
        )
        return

    diagnosticar_ucbt_residenciais(
        df_total_ctmt=df,
        df_residencial=df_residencial,
        clas_sub_prefixo=clas_sub_prefixo,
    )

    salvar_diagnostico_csv(
        df_residencial=df_residencial,
        arquivo_saida=arquivo_diagnostico_csv,
    )

    df_json = separar_dataframe_para_json(
        df_residencial=df_residencial,
    )

    df_ramais = separar_dataframe_para_ramais(
        df_residencial=df_residencial,
    )

    if df_json.empty:
        print("Aviso: nenhum registro válido para JSON por bairro.")
    else:
        resultado_json = gerar_dicionario_bairro_pacs(
            df_json=df_json,
        )

        salvar_json(
            resultado=resultado_json,
            arquivo_json=arquivo_json,
        )

        print("\nExemplo dos primeiros bairros no JSON:")
        exemplo = dict(list(resultado_json.items())[:5])
        print(
            json.dumps(
                exemplo,
                ensure_ascii=False,
                indent=4,
            )
        )

    if df_ramais.empty:
        print("Aviso: nenhum registro válido para arquivo de ramais.")
    else:
        salvar_ramais_txt(
            df_ramais=df_ramais,
            arquivo_saida=arquivo_loads_dss,
        )

    print("\n" + "=" * 80)
    print("Extração concluída")
    print("=" * 80)
    print(f"Total residencial filtrado: {len(df_residencial)}")
    print(f"Total válido para JSON por bairro: {len(df_json)}")
    print(f"Total válido para arquivo de ramais: {len(df_ramais)}")

    if arquivo_json:
        print(f"Arquivo JSON gerado: {arquivo_json.resolve()}")

    if arquivo_loads_dss:
        print(f"Arquivo ramais/loads gerado: {arquivo_loads_dss.resolve()}")

    if arquivo_diagnostico_csv:
        print(f"Arquivo diagnóstico gerado: {arquivo_diagnostico_csv.resolve()}")

    print("=" * 80)