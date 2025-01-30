import os
import pandas as pd
from db_utils import minio_utils

CURRENT_PREFIX = "current/"
invoice_validation_data = minio_utils.minio_to_dataframe(
    minio_bucket='invoice-data-processing.po-invoice-email-data',
    filename_prefix_override=f"{CURRENT_PREFIX}",
)


def pull_invoice_pdf(inv_name, bucket):
    save_path = inv_name.split('/')[-1]
    save_path = os.path.join('pdfs',save_path)
    minio_utils.minio_to_file(filename=save_path,
                                minio_filename_override=inv_name,
                                minio_bucket=bucket
                                )
    return save_path


df = pd.read_parquet('line_item_test_gpt4o.parquet')
ocr = pd.read_parquet('pdf.parquet')

line_items = []
for index, row in df.iterrows():
    lines = row['line_items'][0]
    for line in lines:
        tmp = row.drop(index=['line_items'])
        tmp = tmp.to_dict()
        tmp.update(line)
        line_items.append(tmp)

line_items = pd.DataFrame(line_items)

def convert_to_float(value):
    try:
        # Remove currency symbols (R, ZAR) and spaces
        value = value.replace('R', '').replace('ZA', '').strip()
        # Replace commas used as thousands separators
        value = value.replace(',', '')
        # Replace spaces in numbers like '1 200.00'
        value = value.replace(' ', '')
        # Convert to float
        return float(value)
    except ValueError:
        # Return NaN if conversion fails
        return float('nan')


line_items['amount'] = line_items['amount'].apply(convert_to_float)
line_items['price'] = line_items['price'].apply(convert_to_float)

val = minio_utils.minio_to_dataframe(
    minio_bucket='fleet-data-pipeline.purchase-requisition-purchase-order-items', 
    filename_prefix_override='current',
    filters=[('purchase_order_number', 'in', line_items.purchase_order_number.unique())]
    )

val_cols = [
    'purchase_requisition_description', 'material_description', 'description',
    'purchase_order_number', 'quantity', 'units', 
    'purchase_order_quantity', 'purchase_order_units', 'net_unit_price',
    'net_order_value', 'gross_order_value', 'effective_value'
    ]

val = val[val_cols].reset_index(drop=True)

# Po numbers
val.groupby('purchase_order_number').size().sort_values(ascending=False)

# Pick one and compare
tmp_line_items = line_items[line_items.purchase_order_number == '4502762321']
tmp_val = val[val.purchase_order_number == '4502762321']

# Compare
# parse the tmp_val to a dictionary with purchase_order_number item description qty price
tmp_val[['purchase_order_number', 'description', 'quantity', 'net_unit_price']].to_dict('records')
tmp_line_items[['purchase_order_number', 'item', 'description', 'quantity', 'amount', 'price']].to_dict('records')

print(f'''
Total extracted:  R {round(tmp_line_items['amount'].sum(), 2)}
Total validation: R {tmp_val['net_order_value'].sum()}
Match:            {round(tmp_line_items['amount'].sum(), 2) == tmp_val['net_order_value'].sum()}
''')

pull_invoice_pdf(
    ocr[ocr['object_id'].isin(tmp_line_items.object_id)].path.values[0],
    'fleet-data-pipeline.invoice-examples'
    )