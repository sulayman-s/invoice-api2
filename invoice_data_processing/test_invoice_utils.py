import os
import json

import pandas as pd
import pytesseract

from db_utils import minio_utils
import invoice_utils as iu
from validate_invoice import validation_set, validate_invoice


file_path = os.path.dirname(os.path.abspath(__file__))
os.chdir(file_path)

pdf = minio_utils.minio_to_dataframe('rvanwyk18.invoice-ocr-pdf')
image = minio_utils.minio_to_dataframe('rvanwyk18.invoice-ocr-img')

val = validation_set()

# Combine pdf and image object_ids, then filter val
combined_object_ids = pd.concat([pdf.object_id, image.object_id])
val = val[val.object_id.isin(combined_object_ids)].reset_index(drop=True)

# do the whole pipeline for each invoice
data = []
codes_df = []
df = pd.concat([pdf,image]).reset_index(drop=True)
for row in df.itertuples():
    try:
        llm_raw = iu.llm_key_extraction(row.extract)
        llm_clean = iu.val_clean(llm_raw)
        llm_clean['raw_text'] = row.extract
        llm_clean['source'] = row.path
        llm_clean['object_id'] = row.object_id
        llm_clean['invoice_quality'] = row.invoice_quality 

        # validations
        val_set = val[val.object_id == row.object_id].to_dict(orient='records')[0]
        codes = validate_invoice(llm_clean, val_set)
        codes['object_id'] = row.object_id
        codes['invoice_quality'] = row.invoice_quality
        data.append(llm_clean)
        codes_df.append(codes)
    except Exception as e:
        print(e)


data = pd.DataFrame(data)
codes_df = pd.DataFrame(codes_df)

data.net_amount = pd.to_numeric(data.net_amount, errors='coerce')
data.tax_amount = pd.to_numeric(data.tax_amount, errors='coerce')
data.total_amount = pd.to_numeric(data.total_amount, errors='coerce')

#data.to_parquet('data_gpt40.parquet')
#codes_df.to_parquet('codes_gpt40.parquet')

minio_utils.dataframe_to_minio(
    dataframe=data, 
    minio_bucket='rvanwyk18.invoice-llm-extracted', 
    file_format='parquet'
    )

minio_utils.dataframe_to_minio(
    dataframe=codes_df, 
    minio_bucket='rvanwyk18.invoice-llm-scores', 
    file_format='parquet'
    )

# calculate accuracy from table
codes_df.drop(columns=['object_id'], inplace=True)
codes_df = codes_df.groupby('invoice_quality').sum()

codes_df.groupby('invoice_quality').size()
