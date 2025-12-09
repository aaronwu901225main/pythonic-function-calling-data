You are tasked with generating function signatures based on a given scenario. Follow these steps carefully:

1. Read the following scenario:
<scenario>
{{scenario}}
</scenario>

2. Based on the scenario, generate function signatures that cover the possible operations needed. For each function, you MUST provide:
   - Function name (descriptive and clear)
   - Function parameters with type annotations (str, int, float, bool, List[type], Dict[str, type])
   - Return type annotation (Dict[str, Any] for complex returns, or specific types)
   - Complete docstring including:
     * Brief description of what the function does
     * :param lines for EACH parameter with detailed description
     * :return_fields: section listing ALL fields in the return dictionary with their types and descriptions
     * :raises: section if applicable
   - Expected return value example

CRITICAL REQUIREMENTS for return type documentation:
- If return type is Dict[str, Any], you MUST document all fields in :return_fields: section
- Each field must specify: name, type, and description
- Use this format:
  :return_fields:
    - field_name (type): Description of what this field contains.
    - another_field (type): Description of this field.

Example output format:

<function>
<signature>
```python
def add_to_watchlist(stock: str) -> Dict[str, str]:
    """Add a stock to the watchlist.
    
    :param stock: The stock symbol to add to the watchlist.
    :return_fields:
      - symbol (str): The symbol that was successfully added to the watchlist.
    :raises ValueError: If the stock symbol is invalid.
    """
    pass
```
</signature>
<expected>
{"symbol": "AAPL"}
</expected>
</function>

<function>
<signature>
```python
def get_account_info() -> Dict[str, Any]:
    """Get account information.
    
    :return_fields:
      - account_id (int): ID of the account.
      - balance (float): Current balance of the account.
      - binding_card (int): Card number associated with the account.
    """
    pass
```
</signature>
<expected>
{"account_id": 12345, "balance": 10000.50, "binding_card": 987654321}
</expected>
</function>

<function>
<signature>
```python
def filter_stocks_by_price(stocks: List[str], min_price: float, max_price: float) -> Dict[str, List[str]]:
    """Filter stocks based on a price range.
    
    :param stocks: List of stock symbols to filter.
    :param min_price: Minimum stock price.
    :param max_price: Maximum stock price.
    :return_fields:
      - filtered_stocks (List[str]): Filtered list of stock symbols within the price range.
    :raises ValueError: If min_price is greater than max_price.
    """
    pass
```
</signature>
<expected>
{"filtered_stocks": ["AAPL", "GOOGL", "MSFT"]}
</expected>
</function>

<function>
<signature>
```python
def send_message(receiver_id: str, message: str) -> Dict[str, Any]:
    """Send a message to a user.
    
    :param receiver_id: User ID of the user to send the message to.
    :param message: Message to be sent.
    :return_fields:
      - sent_status (bool): True if the message was sent successfully, False otherwise.
      - message_id (int): ID of the sent message.
      - message (str): A message describing the result of the send attempt.
    """
    pass
```
</signature>
<expected>
{"sent_status": true, "message_id": 12345, "message": "Message sent successfully"}
</expected>
</function>

IMPORTANT NOTES:
1. Use proper Python type hints: str, int, float, bool, List[type], Dict[str, type]
2. Return type should be Dict[str, Any] for complex objects, or Dict[str, specific_type] when all values are same type
3. ALWAYS include :return_fields: section for Dict return types with ALL fields documented
4. Each parameter description should end with a period
5. Keep descriptions clear and concise
6. The expected value should match the documented return fields exactly

Generate as many functions as necessary to cover the scenario comprehensively, with each function enclosed in <function> tags.