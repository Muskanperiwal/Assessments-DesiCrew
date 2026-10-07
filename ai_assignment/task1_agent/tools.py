"""Tools for Task 1: Autonomous Data Analyst Agent.
Provides Python/Pandas code execution and web search capabilities.
"""
import io
import sys
import traceback
import pandas as pd
import numpy as np

def clean_code(code: str) -> str:
    """Strip markdown code fence blocks if present."""
    code_lines = [line for line in code.strip().split('\n') if not line.strip().startswith('```')]
    return '\n'.join(code_lines).strip()

def execute_pandas_code(code: str, df: pd.DataFrame) -> dict:
    """
    Executes Python code safely against the provided Pandas DataFrame.
    Captures stdout and any returned or assigned 'result' variable.
    
    Args:
        code: The Python code snippet to execute.
        df: The pandas DataFrame representing inventory records.
        
    Returns:
        dict containing 'success', 'output', and 'error'.
    """
    cleaned = clean_code(code)
    local_scope = {
        'df': df.copy(),
        'pd': pd,
        'np': np,
        'result': None
    }
    
    # Check if last line is an expression and can assign to 'result'
    lines = cleaned.strip().split('\n')
    if lines and not lines[-1].startswith(' ') and not lines[-1].startswith('\t'):
        last_line = lines[-1].strip()
        if not (last_line.startswith('print') or '=' in last_line or last_line.startswith('import') or last_line.startswith('def ') or last_line.startswith('for ') or last_line.startswith('if ')):
            lines[-1] = f"result = ({last_line})"
            cleaned = '\n'.join(lines)

    stdout_capture = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = stdout_capture

    try:
        exec(cleaned, local_scope, local_scope)
        sys.stdout = old_stdout
        captured_stdout = stdout_capture.getvalue()

        res = local_scope.get('result')
        formatted_output = ""

        if isinstance(res, (pd.DataFrame, pd.Series)):
            formatted_output = str(res)
        elif isinstance(res, (int, float, np.integer, np.floating)):
            formatted_output = f"{res:,.2f}" if isinstance(res, float) else f"{res:,}"
        elif res is not None:
            formatted_output = str(res)

        output = captured_stdout.strip()
        if formatted_output and output:
            output = f"{output}\n\n{formatted_output}"
        elif formatted_output:
            output = formatted_output
        elif not output:
            output = "Execution completed with no printed output."

        return {
            "success": True,
            "output": output,
            "error": None,
            "code": cleaned
        }
    except Exception as e:
        sys.stdout = old_stdout
        return {
            "success": False,
            "output": stdout_capture.getvalue().strip(),
            "error": f"{type(e).__name__}: {str(e)}",
            "code": cleaned
        }

def search_web(query: str, max_results: int = 3) -> dict:
    """
    Performs live web search for contextual queries (e.g. industry benchmarks, product info).
    
    Args:
        query: Search string.
        max_results: Max results to retrieve.
        
    Returns:
        dict containing 'success', 'query', and 'results'.
    """
    query = query.strip()
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            raw_results = list(ddgs.text(query, max_results=max_results))
            
        formatted = []
        for r in raw_results:
            formatted.append({
                "title": r.get("title", ""),
                "snippet": r.get("body", "") or r.get("snippet", ""),
                "url": r.get("href", "") or r.get("link", "")
            })
            
        return {
            "success": True,
            "query": query,
            "results": formatted
        }
    except Exception as e:
        return {
            "success": False,
            "query": query,
            "error": str(e),
            "results": []
        }
