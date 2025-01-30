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

pdf = pdf[pdf['fiscal_year'].isin([2021, 2020])].reset_index(drop=True)
image = image[image['fiscal_year'].isin([2021, 2020])].reset_index(drop=True)

val = validation_set()

# Combine pdf and image object_ids, then filter val
combined_object_ids = pd.concat([pdf.object_id, image.object_id])
val = val[val.object_id.isin(combined_object_ids)].reset_index(drop=True)

# save
pdf.to_parquet('pdf.parquet')
image.to_parquet('image.parquet')
val.to_parquet('val.parquet')

# load
pdf = pd.read_parquet('../tests/pdf.parquet')
image = pd.read_parquet('../tests/image.parquet')
val = pd.read_parquet('../tests/val.parquet')

# do the whole pipeline for each invoice
data = []
codes_df = []
for row in pdf.itertuples():
    llm_raw = iu.llm_key_extraction(row.extract)
    llm_clean = iu.val_clean(llm_raw)
    llm_clean['object_id'] = row.object_id
    llm_clean['invoice_quality'] = 'pdf'

    # validations
    val_set = val[val.object_id == row.object_id].to_dict(orient='records')[0]
    codes = validate_invoice(llm_clean, val_set)
    if codes['bank_account_number'] == False:
        if val_set['bank_account_number'] in row.extract:
            codes['bank_account_number'] = True
            llm_clean['bank_account_number'] = val_set['bank_account_number']
    codes['object_id'] = row.object_id
    codes['invoice_quality'] = 'pdf'
    data.append(llm_clean)
    codes_df.append(codes)

# do the same for image
for row in image.itertuples():
    llm_raw = iu.llm_key_extraction(row.extract)
    llm_clean = iu.val_clean(llm_raw)
    llm_clean['object_id'] = row.object_id
    llm_clean['invoice_quality'] = 'img'

    # validations
    val_set = val[val.object_id == row.object_id].to_dict(orient='records')[0]
    codes = validate_invoice(llm_clean, val_set)
    if codes['bank_account_number'] == False:
        if val_set['bank_account_number'] in row.extract:
            codes['bank_account_number'] = True
            llm_clean['bank_account_number'] = val_set['bank_account_number']
    codes['object_id'] = row.object_id
    codes['invoice_quality'] = 'img'
    data.append(llm_clean)
    codes_df.append(codes)

data = pd.DataFrame(data)
codes_df = pd.DataFrame(codes_df)

data.net_amount = pd.to_numeric(data.net_amount, errors='coerce')
data.tax_amount = pd.to_numeric(data.tax_amount, errors='coerce')

#data.to_parquet('data_gpt40.parquet')
#codes_df.to_parquet('codes_gpt40.parquet')

# calculate accuracy from table
codes_df.drop(columns=['object_id'], inplace=True)
codes_df = codes_df.groupby('invoice_quality').sum()

codes_df.groupby('invoice_quality').size()