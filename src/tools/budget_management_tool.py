# src/tools/budget_management_tool.py

import requests
import json
import re
from typing import Dict, List, Any, Optional
from datetime import datetime
from src.config.config import config
from src.utils.logging_utils import get_logger
from src.constants.transactionCategories import (
    TRANSACTION_CATEGORIES,
    CATEGORY_KEYWORDS,
    DEFAULT_CATEGORY,
)

logger = get_logger(__name__)


def get_current_month_year():
    """Helper function to get current month-year in different formats"""
    current_date = datetime.now()
    return {
        'month_year_string': current_date.strftime("%Y-%m"),  # For GraphQL queries
        'month_int': current_date.month,  # For CSV exports
        'year_int': current_date.year,    # For CSV exports
        'display_format': current_date.strftime("%B %Y")  # For logging/display
    }


def detect_category(description: str) -> str:
    """
    Smart category detection based on expense description.
    Returns the most likely category or DEFAULT_CATEGORY if no match found.
    """
    if not description:
        return DEFAULT_CATEGORY

    description_lower = description.lower()

    # Score each category based on keyword matches
    category_scores = {}

    for category, keywords in CATEGORY_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            if keyword.lower() in description_lower:
                # Give higher score for exact matches and longer keywords
                score += len(keyword.split())
        category_scores[category] = score

    # Find the category with the highest score
    if category_scores:
        best_category = max(category_scores.items(), key=lambda x: x[1])
        if best_category[1] > 0:  # Only return if we found a match
            return best_category[0]

    # Fallback to default category
    return DEFAULT_CATEGORY


class BudgetManagementClient:
    def __init__(self):
        self.url = config.graphql_server_url
        self.headers = {
            "Content-Type": "application/json",
            "X-API-Token": config.graphql_api_token,
        }

    def _execute_query(self, query: str, variables: Dict = None) -> Dict[str, Any]:
        """Execute a GraphQL query/mutation"""
        payload = {"query": query, "variables": variables or {}}

        try:
            response = requests.post(self.url, json=payload, headers=self.headers)
            response.raise_for_status()
            result = response.json()

            if "errors" in result:
                logger.error(f"GraphQL errors: {result['errors']}")
                raise Exception(f"GraphQL errors: {result['errors']}")

            return result.get("data", {})
        except requests.RequestException as e:
            logger.error(f"Request failed: {e}")
            raise Exception(f"Request failed: {e}")

    def add_expense(
        self, description: str, amount: float, category: str
    ) -> Dict[str, Any]:
        """Add a new expense transaction"""
        mutation = """
            mutation AddTransaction($input: TransactionInput!) {
                addTransaction(input: $input) {
                    id
                    description
                    amount
                    category
                    createdAt
                }
            }
        """
        variables = {
            "input": {
                "description": description,
                "amount": str(amount),
                "category": category,
            }
        }
        return self._execute_query(mutation, variables)

    def add_income(self, source: str, amount: float) -> Dict[str, Any]:
        """Add a new income entry"""
        mutation = """
            mutation AddIncome($input: IncomeInput!) {
                addIncome(input: $input) {
                    id
                    source
                    amount
                    receivedAt
                }
            }
        """
        variables = {"input": {"source": source, "amount": str(amount)}}
        return self._execute_query(mutation, variables)

    def get_transactions(self) -> Dict[str, Any]:
        """Get all transactions"""
        query = """
            query GetTransactions {
                transactions {
                    id
                    description
                    amount
                    category
                    createdAt
                }
            }
        """
        return self._execute_query(query)

    def get_incomes(self) -> Dict[str, Any]:
        """Get all income entries"""
        query = """
            query GetIncomes {
                incomes {
                    id
                    source
                    amount
                    receivedAt
                }
            }
        """
        return self._execute_query(query)

    def get_savings(self) -> Dict[str, Any]:
        """Get all savings entries"""
        query = """
            query GetSavings {
                savings {
                    id
                    name
                    amount
                    savedAt
                }
            }
        """
        return self._execute_query(query)

    def get_monthly_remain(self, month: str) -> Dict[str, Any]:
        """Get monthly financial summary"""
        query = """
            query GetMonthlyRemain($month: String!) {
                monthlyRemain(month: $month) {
                    month
                    totalIncome
                    totalExpense
                    expenses {
                        id
                        category
                        amount
                    }
                    remain
                }
            }
        """
        variables = {"month": month}
        return self._execute_query(query, variables)

    def export_unified_csv(
        self,
        month: Optional[int] = None,
        year: Optional[int] = None,
        all_data: bool = False,
    ) -> str:
        """Export data as CSV"""
        mutation = """
            mutation ExportUnified($month: Int, $year: Int, $all: Boolean) {
                exportUnifiedCsv(month: $month, year: $year, all: $all)
            }
        """
        variables = {"month": month, "year": year, "all": all_data}
        result = self._execute_query(mutation, variables)
        return result.get("exportUnifiedCsv", "")


# Initialize the client
budget_client = BudgetManagementClient()


def add_expense_tool(
    description: str, amount: float, category: str = None
) -> Dict[str, Any]:
    """Add a new expense transaction to the budget system. If category is not provided, it will be automatically detected."""
    try:
        # Use smart category detection if no category provided
        if not category:
            category = detect_category(description)
            logger.info(
                f"Auto-detected category '{category}' for expense: {description}"
            )

        result = budget_client.add_expense(description, amount, category)
        logger.info(f"Added expense: {description} - ${amount} ({category})")
        return result
    except Exception as e:
        logger.error(f"Failed to add expense: {e}")
        return {"error": str(e)}


def add_income_tool(source: str, amount: float) -> Dict[str, Any]:
    """Add a new income entry to the budget system."""
    try:
        result = budget_client.add_income(source, amount)
        logger.info(f"Added income: {source} - ${amount}")
        return result
    except Exception as e:
        logger.error(f"Failed to add income: {e}")
        return {"error": str(e)}


def get_budget_summary_tool(month: Optional[str] = None) -> Dict[str, Any]:
    """Get comprehensive budget summary including transactions, incomes, and savings.
    If no month is specified, uses current month (YYYY-MM format)."""
    try:
        summary = {}

        # Get all financial data
        summary["transactions"] = budget_client.get_transactions()
        summary["incomes"] = budget_client.get_incomes()
        summary["savings"] = budget_client.get_savings()

        # If no month specified, use current month
        if not month:
            current_info = get_current_month_year()
            month = current_info['month_year_string']
            logger.info(f"No month specified, using current month: {month} ({current_info['display_format']})")

        # Get monthly summary
        summary["monthly_summary"] = budget_client.get_monthly_remain(month)
        summary["month_analyzed"] = month

        logger.info(f"Retrieved budget summary for month: {month}")
        return summary
    except Exception as e:
        logger.error(f"Failed to get budget summary: {e}")
        return {"error": str(e)}


def get_expense_report_tool(
    month: Optional[int] = None, year: Optional[int] = None, all_data: bool = False
) -> str:
    """Generate and export expense report in CSV format.
    If no month/year specified and all_data is False, defaults to current month/year."""
    try:
        # If no specific parameters and not requesting all data, default to current month/year
        if not all_data and month is None and year is None:
            current_info = get_current_month_year()
            month = current_info['month_int']
            year = current_info['year_int']
            logger.info(f"No date specified, using current month/year: {month}/{year} ({current_info['display_format']})")

        csv_data = budget_client.export_unified_csv(month, year, all_data)
        logger.info(
            f"Generated expense report - Month: {month}, Year: {year}, All: {all_data}"
        )
        return csv_data
    except Exception as e:
        logger.error(f"Failed to generate expense report: {e}")
        return f"Error generating report: {str(e)}"


def get_available_categories_tool() -> Dict[str, Any]:
    """Get list of available expense categories."""
    return {"categories": TRANSACTION_CATEGORIES, "total": len(TRANSACTION_CATEGORIES)}


def predict_category_tool(description: str) -> Dict[str, str]:
    """Predict the most appropriate category for an expense description."""
    predicted_category = detect_category(description)
    return {"description": description, "predicted_category": predicted_category}
