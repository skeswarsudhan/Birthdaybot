"""
data_source/__init__.py

Factory function that returns the correct EmployeeDataSource implementation
based on the DATA_SOURCE environment variable.

The rest of the codebase should ALWAYS call get_data_source() and never
import ExcelDataSource or SharePointDataSource directly.
"""

from config import DATA_SOURCE


def get_data_source():
    """
    Return the configured EmployeeDataSource implementation.

    Reads DATA_SOURCE from environment:
      - 'excel'      → ExcelDataSource (default, POC)
      - 'sharepoint' → SharePointDataSource (stub, raises NotImplementedError)

    Raises:
        ValueError: if DATA_SOURCE is set to an unknown value.
    """
    if DATA_SOURCE == "excel":
        from data_source.excel_reader import ExcelDataSource
        return ExcelDataSource()
    elif DATA_SOURCE == "sharepoint":
        from data_source.sharepoint_reader import SharePointDataSource
        return SharePointDataSource()
    else:
        raise ValueError(
            f"Unknown DATA_SOURCE: '{DATA_SOURCE}'. "
            "Valid values are 'excel' or 'sharepoint'."
        )
