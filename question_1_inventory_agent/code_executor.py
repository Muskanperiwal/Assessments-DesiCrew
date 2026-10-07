import io
import sys
import traceback
import pandas as pd
import numpy as np

class PythonCodeExecutor:
    """
    Executes Python/Pandas code securely against an active DataFrame,
    capturing standard output, evaluated results, and structured tables.
    """
    def __init__(self):
        pass

    def execute(self, code_str: str, df: pd.DataFrame) -> dict:
        """
        Executes code_str in a local environment where 'df', 'pd', 'np' are bound.
        Returns a dictionary containing status, stdout, result representation, and tabular data if available.
        """
        # Create dedicated execution context
        # Provide a copy of df so mutations do not unintentionally corrupt main dataset
        local_scope = {
            'df': df.copy(),
            'pd': pd,
            'np': np,
            'result': None
        }

        stdout_capture = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = stdout_capture

        try:
            # Clean code string
            code_lines = [line for line in code_str.strip().split('\n') if not line.startswith('```')]
            clean_code = '\n'.join(code_lines)

            # Check if last line is an expression and can assign to 'result'
            lines = clean_code.strip().split('\n')
            if lines and not lines[-1].startswith(' ') and not lines[-1].startswith('\t'):
                last_line = lines[-1].strip()
                if not (last_line.startswith('print') or '=' in last_line or last_line.startswith('import') or last_line.startswith('def ') or last_line.startswith('for ') or last_line.startswith('if ')):
                    lines[-1] = f"result = ({last_line})"
                    clean_code = '\n'.join(lines)

            exec(clean_code, local_scope, local_scope)
            sys.stdout = old_stdout
            captured_stdout = stdout_capture.getvalue()

            res = local_scope.get('result')

            # Format result
            table_data = None
            result_summary = ""

            if isinstance(res, pd.DataFrame):
                # Convert DataFrame to records for UI rendering
                table_data = {
                    "columns": list(res.columns),
                    "rows": res.fillna("").to_dict(orient='records'),
                    "shape": list(res.shape)
                }
                result_summary = f"DataFrame with {res.shape[0]} rows and {res.shape[1]} columns."
            elif isinstance(res, pd.Series):
                res_df = res.reset_index()
                table_data = {
                    "columns": list(res_df.columns),
                    "rows": res_df.fillna("").to_dict(orient='records'),
                    "shape": list(res_df.shape)
                }
                result_summary = f"Series with {len(res)} elements."
            elif isinstance(res, (int, float, np.integer, np.floating)):
                result_summary = f"{res:,.2f}" if isinstance(res, float) else f"{res:,}"
            elif res is not None:
                result_summary = str(res)
            else:
                result_summary = captured_stdout.strip() if captured_stdout else "Execution completed successfully."

            return {
                "success": True,
                "executed_code": clean_code,
                "stdout": captured_stdout,
                "result": result_summary,
                "table_data": table_data
            }

        except Exception as e:
            sys.stdout = old_stdout
            err_msg = traceback.format_exc()
            return {
                "success": False,
                "executed_code": code_str,
                "error": str(e),
                "traceback": err_msg
            }
