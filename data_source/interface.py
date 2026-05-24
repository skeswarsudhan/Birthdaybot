"""
data_source/interface.py — Abstract base class for all employee data sources.

Any new data source (Excel, SharePoint, HR API, etc.) must subclass
EmployeeDataSource and implement get_employees().
"""

from abc import ABC, abstractmethod


class EmployeeDataSource(ABC):
    """
    Contract for all employee data sources.

    Implementing classes must return a list of dicts where each dict
    represents one employee with the keys defined below.
    """

    @abstractmethod
    def get_employees(self) -> list[dict]:
        """
        Fetch all employees from the underlying data source.

        Returns:
            A list of dicts, each containing:
                name          (str)  — Full display name
                email         (str)  — Work email address
                dob           (date) — Date of birth (date object, not string)
                manager_name  (str)  — Manager's display name
                manager_email (str)  — Manager's email address
                department    (str)  — Department / cost centre name
                active        (bool) — Whether the employee is currently active
        """
        ...
