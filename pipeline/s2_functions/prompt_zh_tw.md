````markdown
你的任務是根據給定的情境生成函數簽名。請仔細遵循以下步驟：

1. 閱讀以下情境：
<scenario>
{{scenario}}
</scenario>

2. 根據情境，生成涵蓋所需操作的函數簽名。對於每個函數，你必須提供：
   - 函數名稱（描述性且清晰，使用英文命名）
   - 帶有類型註解的函數參數（str, int, float, bool, List[type], Dict[str, type]）
   - 返回類型註解（複雜返回使用 Dict[str, Any]，或使用特定類型）
   - 完整的文檔字串（docstring），包括：
     * 函數功能的簡要描述（使用繁體中文）
     * 每個參數的 :param 行，附帶詳細描述（使用繁體中文）
     * :return_fields: 區段，列出返回字典中的所有欄位及其類型和描述（使用繁體中文）
     * :raises: 區段（如適用，使用繁體中文）
   - 預期返回值範例

關於返回類型文檔的關鍵要求：
- 如果返回類型是 Dict[str, Any]，你必須在 :return_fields: 區段中記錄所有欄位
- 每個欄位必須指定：名稱、類型和描述
- 使用以下格式：
  :return_fields:
    - field_name (type): 此欄位包含的內容描述。
    - another_field (type): 此欄位的描述。

輸出格式範例：

<function>
<signature>
```python
def add_to_watchlist(stock: str) -> Dict[str, str]:
    """將股票加入關注清單。
    
    :param stock: 要加入關注清單的股票代碼。
    :return_fields:
      - symbol (str): 成功加入關注清單的股票代碼。
    :raises ValueError: 如果股票代碼無效。
    """
    pass
```
</signature>
<expected>
{"symbol": "2330"}
</expected>
</function>

<function>
<signature>
```python
def get_account_info() -> Dict[str, Any]:
    """取得帳戶資訊。
    
    :return_fields:
      - account_id (int): 帳戶識別碼。
      - balance (float): 帳戶目前餘額。
      - binding_card (int): 綁定的卡片號碼。
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
    """根據價格範圍篩選股票。
    
    :param stocks: 要篩選的股票代碼列表。
    :param min_price: 最低股價。
    :param max_price: 最高股價。
    :return_fields:
      - filtered_stocks (List[str]): 在價格範圍內的已篩選股票代碼列表。
    :raises ValueError: 如果最低價格大於最高價格。
    """
    pass
```
</signature>
<expected>
{"filtered_stocks": ["2330", "2317", "2454"]}
</expected>
</function>

<function>
<signature>
```python
def send_message(receiver_id: str, message: str) -> Dict[str, Any]:
    """發送訊息給用戶。
    
    :param receiver_id: 接收訊息的用戶 ID。
    :param message: 要發送的訊息內容。
    :return_fields:
      - sent_status (bool): 如果訊息發送成功則為 True，否則為 False。
      - message_id (int): 已發送訊息的 ID。
      - message (str): 描述發送結果的訊息。
    """
    pass
```
</signature>
<expected>
{"sent_status": true, "message_id": 12345, "message": "訊息發送成功"}
</expected>
</function>

重要注意事項：
1. 使用正確的 Python 類型提示：str, int, float, bool, List[type], Dict[str, type]
2. 複雜物件的返回類型應為 Dict[str, Any]，或當所有值為相同類型時使用 Dict[str, specific_type]
3. 對於 Dict 返回類型，必須包含 :return_fields: 區段並記錄所有欄位
4. 每個參數描述應以句號結尾
5. 描述保持清晰簡潔
6. 預期值應與記錄的返回欄位完全匹配
7. 函數名稱使用英文，但 docstring 內容使用繁體中文

生成足夠的函數以全面涵蓋情境，每個函數都用 <function> 標籤包裹。
````
