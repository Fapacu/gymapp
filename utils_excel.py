import pandas as pd
from io import BytesIO

def df_to_excel_download(df: pd.DataFrame, filename: str = "export.xlsx") -> tuple[bytes, str]:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    bio.seek(0)
    return bio.read(), filename
