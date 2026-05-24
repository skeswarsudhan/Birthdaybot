"""
data_source/sharepoint_reader.py — SharePoint data source stub.

This is a placeholder for a future Azure AD / SharePoint integration.
Set DATA_SOURCE=sharepoint in .env only after the Azure AD app registration
has been approved and the MSAL credentials are configured.
"""

from data_source.interface import EmployeeDataSource


class SharePointDataSource(EmployeeDataSource):
    """
    Stub SharePoint data source — raises NotImplementedError on use.

    Future implementation will use the Microsoft Graph API via MSAL.
    See README.md for the planned integration architecture.
    """

    def get_employees(self) -> list[dict]:
        """
        Not yet implemented.

        Raises:
            NotImplementedError: Always. Switch to DATA_SOURCE=excel until
                the Azure AD integration is complete.
        """
        raise NotImplementedError(
            "SharePoint integration is pending Azure AD app registration approval. "
            "Set DATA_SOURCE=excel in your .env file to use the Excel reader instead."
        )
