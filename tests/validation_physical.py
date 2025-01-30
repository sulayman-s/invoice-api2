import json
import os
import pandas as pd

path = os.path.dirname(os.path.abspath(__file__))
json_path = os.path.join(path, '../invoice_data_processing/jsons')

files = [os.path.join(json_path, f) for f in os.listdir(json_path) if f.endswith('compare.json')]

data = []
for file in files:
    with open(file, 'r') as f:
        data.append(json.load(f))

df = pd.DataFrame(data)
# split line_items to new dataframe

line_items = []
for items in df['line_items']:
    for item in items:
        line_items.append(item)

line_items = pd.DataFrame(line_items)
df.drop(columns=['line_items'], inplace=True)

bank_details = []
for items in df['bank_details']:
    if items is not None:
        bank_details.append(item)
    else:
        bank_details.append({'bank_name': True, 'bank_branch_code': True, 'bank_account_number': True})

bank_details = pd.DataFrame(bank_details)
df.drop(columns=['bank_details'], inplace=True)

cols = [
    'purchase_order_number', 'vendor_name',
    'vendor_invoice_id', 'vendor_tax_id', 'vendor_registration_number',
    'vendor_address', 'net_amount', 'total_amount', 'tax_amount'
    ]

df['all_true'] = df[cols].all(axis=1)
df.groupby('file_type').sum().div(df.groupby('file_type').size(), axis=0)

line_items.sum().div(line_items.shape[0], axis=0)
bank_details.sum().div(bank_details.shape[0], axis=0)
