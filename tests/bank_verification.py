import pandas as pd
from validate_invoice import validation_set

val = validation_set()

gpt = pd.read_parquet('../tests/data_gpt40.parquet')
son = pd.read_parquet('../tests/data_sonnet3_5.parquet')

pdf = pd.read_parquet('../tests/pdf.parquet')
image = pd.read_parquet('../tests/image.parquet')

text = pd.concat([pdf,image])

gpt = gpt.merge(text[['object_id','extract']], on='object_id', how='left')
son = son.merge(text[['object_id','extract']], on='object_id', how='left')

def fail_flag(ai, val):
    cols = ['purchase_order_number', 'bank_account_number', 'total_amount']

    for col in cols:
        if col == 'total_amount':
            if ai['total_amount'] != val['invoice_value']:
                return True
        elif ai[col] != val[col]:
            return True
    return False

data = []
for index, row in gpt.iterrows():
    d = {}
    v = val[val.object_id == row['object_id']].to_dict(orient='records')[0]
    d['model'] = 'gpt4o'
    d['object_id'] = row['object_id']
    d['invoice_quality'] = row['invoice_quality']
    d['extract'] = row['extract']
    d['ai_purchase_order_number'] = row['purchase_order_number']
    d['ven_purchase_order_number'] = v['purchase_order_number']
    d['ai_vendor_name'] = row['vendor_name']
    d['ven_vendor_name'] = v['vendor_name']
    d['ai_bank_name'] = row['bank_name']
    d['ven_bank_name'] = v['bank_name']
    d['ai_bank_account_number'] = row['bank_account_number']
    d['ven_bank_account_number'] = v['bank_account_number']
    d['ai_bank_branch_code'] = row['bank_branch_code']
    d['ven_bank_branch_code'] = v['bank_branch_code']
    d['ai_total_amount'] = row['total_amount']
    d['ven_total_amount'] = v['invoice_value']
    if fail_flag(row, v):
        data.append(d)

for index, row in son.iterrows():
    d = {}
    v = val[val.object_id == row['object_id']].to_dict(orient='records')[0]
    d['model'] = 'sonnet3.5'
    d['object_id'] = row['object_id']
    d['invoice_quality'] = row['invoice_quality']
    d['extract'] = row['extract']
    d['ai_purchase_order_number'] = row['purchase_order_number']
    d['ven_purchase_order_number'] = v['purchase_order_number']
    d['ai_vendor_name'] = row['vendor_name']
    d['ven_vendor_name'] = v['vendor_name']
    d['ai_bank_name'] = row['bank_name']
    d['ven_bank_name'] = v['bank_name']
    d['ai_bank_account_number'] = row['bank_account_number']
    d['ven_bank_account_number'] = v['bank_account_number']
    d['ai_bank_branch_code'] = row['bank_branch_code']
    d['ven_bank_branch_code'] = v['bank_branch_code']
    d['ai_total_amount'] = row['total_amount']
    d['ven_total_amount'] = v['invoice_value']
    if fail_flag(row, v):
        data.append(d)

data = pd.DataFrame(data)

data['acc_in_invoice'] = False
for index, row in data.iterrows():
    if row['ven_purchase_order_number'] in row['extract']:
        data.loc[index, 'acc_in_invoice'] = True

data.to_csv('bank_verification.csv')


