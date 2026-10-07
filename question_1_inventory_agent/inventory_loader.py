import pandas as pd
import numpy as np
import os

DEFAULT_EXCEL_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', 'Question 1 & 3 (Files to use)', 'Question 1', 'Inventory-Records-Sample-Data.xlsx'
))

def load_inventory_data(filepath=None):
    """
    Loads and cleans an inventory Excel file.
    Automatically discovers header row and normalizes column headers.
    """
    path_to_use = filepath or DEFAULT_EXCEL_PATH
    if not os.path.exists(path_to_use):
        raise FileNotFoundError(f"Excel file not found at: {path_to_use}")

    # Read the sheet to inspect structure
    raw_df = pd.read_excel(path_to_use, header=None)
    
    # Locate header row by looking for known column terms
    header_idx = None
    for idx, row in raw_df.iterrows():
        row_str = " ".join([str(val).lower() for val in row if pd.notna(val)])
        if 'product id' in row_str or 'product name' in row_str or 'stock' in row_str:
            header_idx = idx
            break
            
    if header_idx is None:
        header_idx = 0

    df = pd.read_excel(path_to_use, header=header_idx)
    # Drop all-NaN columns and rows
    df = df.dropna(how='all', axis=1)
    df = df.dropna(how='all', axis=0)

    # Clean and normalize column names
    clean_cols = []
    for c in df.columns:
        norm = " ".join(str(c).split())
        # Replace common awkward spacing in the raw sheet
        norm = norm.replace("Hand-In- Stock", "Hand-In-Stock")
        norm = norm.replace("Purchase/ Stock in", "Purchase / Stock In")
        norm = norm.replace("Number of Units Sold", "Number of Units Sold")
        clean_cols.append(norm)
    df.columns = clean_cols

    # Standardize column mapping
    col_map = {}
    for col in df.columns:
        c_clean = col.lower()
        if 'product id' in c_clean or 'id' in c_clean:
            col_map[col] = 'Product_ID'
        elif 'product name' in c_clean or 'name' in c_clean:
            col_map[col] = 'Product_Name'
        elif 'opening' in c_clean and 'stock' in c_clean:
            col_map[col] = 'Opening_Stock'
        elif 'purchase' in c_clean or 'stock in' in c_clean:
            col_map[col] = 'Stock_In'
        elif 'sold' in c_clean or 'units sold' in c_clean:
            col_map[col] = 'Units_Sold'
        elif 'hand' in c_clean and 'stock' in c_clean:
            col_map[col] = 'Hand_In_Stock'
        elif 'per unit' in c_clean:
            col_map[col] = 'Unit_Cost_USD'
        elif 'cost price total' in c_clean or ('total' in c_clean and 'cost' in c_clean):
            col_map[col] = 'Total_Cost_USD'

    # Ensure numeric columns are properly typed
    numeric_standards = ['Opening_Stock', 'Stock_In', 'Units_Sold', 'Hand_In_Stock', 'Unit_Cost_USD', 'Total_Cost_USD']
    for original_col, standard_name in col_map.items():
        if standard_name in numeric_standards:
            df[original_col] = pd.to_numeric(df[original_col], errors='coerce').fillna(0)

    return df, col_map, path_to_use

def get_dataset_metadata(df):
    """
    Returns summary statistics, columns, and sample records for UI and agent prompt.
    """
    summary = {
        "total_products": int(len(df)),
        "columns": list(df.columns),
        "data_preview": df.head(10).to_dict(orient='records'),
        "numeric_summary": {}
    }
    
    numeric_df = df.select_dtypes(include=[np.number])
    for col in numeric_df.columns:
        summary["numeric_summary"][col] = {
            "sum": float(df[col].sum()),
            "mean": round(float(df[col].mean()), 2),
            "min": float(df[col].min()),
            "max": float(df[col].max()),
        }
        
    return summary
