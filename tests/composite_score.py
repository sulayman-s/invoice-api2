import pandas as pd

df = pd.read_parquet('codes_sonnet3_5.parquet')
df.drop(columns=['bank_branch_code'], inplace=True)
cols = ['PO','bank_name','bank_account_number','vendor_name','total_amount']

# apply for each row a check to see if all the values in cols is True
df['composite_score'] = df[cols].all(axis=1)
df.groupby('invoice_quality').sum()