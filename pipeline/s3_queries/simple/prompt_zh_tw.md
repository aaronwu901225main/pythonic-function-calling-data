```markdown
你的任務是為給定的函數生成用戶查詢和對應的參數作為函數調用。函數定義如下：

{{function_schema}}

你的任務是：

1. 生成一個需要使用此函數的真實用戶查詢。用戶查詢應明確說明特殊名稱並用雙引號標示。
2. 根據你生成的用戶查詢，提供適當的函數參數作為函數調用
3. 生成 num_query 個不同的查詢-參數對。

使用以下格式作為函數調用：

<function_call>
variable_name = function_name(param_1=value, param_2=value)
</function_call>

<user_query>
[在此處插入生成的用戶查詢]
</user_query>
<function_call>
[在此處插入函數參數]
</function_call>

請確保：
- 用戶查詢與函數的用途相關
- 函數參數準確反映用戶查詢中指定的要求
- 所有用戶查詢必須使用繁體中文撰寫
- 人名使用中文名字（例如：王小明、李美玲）
- 地點、公司名稱等也使用中文

生成 {{num_queries}} 個不同的查詢
```
