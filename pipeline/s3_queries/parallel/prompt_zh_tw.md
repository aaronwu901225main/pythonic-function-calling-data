```markdown
你的任務是為給定的函數生成平行用戶查詢和對應的參數作為函數調用。

平行查詢是指一個需要使用不同參數多次調用同一函數的單一查詢。

函數定義如下：

{{function_schema}}

你的任務是：

1. 生成一個需要使用不同參數調用此函數的真實用戶查詢。用戶查詢應明確說明特殊名稱並用雙引號標示。
2. 根據你生成的用戶查詢，提供適當的函數參數作為函數調用
3. 生成 num_query 個不同的查詢-函數對。

使用以下格式作為函數調用：

<function_calls>
variable_name = function_name(param_1=value, param_2=value)
</function_calls>

<user_query>
[在此處插入生成的平行用戶查詢]
</user_query>
<function_calls>
[在此處插入函數調用]
</function_calls>

範例 #1：

<user_query>
我正在做一些市場調查，我有一份我感興趣的商品列表，商品編號分別是：「B075H2B962」、「B08BHXG144」、「B07ZPKBL9V」和「B08PPDJWC8」。你能幫我查詢這些商品編號對應的產品名稱嗎？
</user_query>
<function_calls>
product_1 = get_product_name_by_amazon_ASIN(ASIN='B075H2B962')
product_2 = get_product_name_by_amazon_ASIN(ASIN='B08BHXG144')
product_3 = get_product_name_by_amazon_ASIN(ASIN='B07ZPKBL9V')
product_4 = get_product_name_by_amazon_ASIN(ASIN='B08PPDJWC8')
</function_calls>

範例 #2：

<user_query>
請幫我將列表 [5, 2, 9, 1, 7] 按升序排序，將 [3, 8, 6, 4] 按降序排序，將 [10, 20, 30, 40, 50] 按升序排序，將 [100, 200, 300, 400, 500] 按降序排序。
</user_query>
<function_calls>
sorted_1_ascending = sort_array(array=[5, 2, 9, 1, 7])
sorted_1_descending= sort_array(array=[3, 8, 6, 4], reverse=True)
sorted_2_ascending = sort_array(array=[10, 20, 30, 40, 50])
sorted_2_descending = sort_array(array=[100, 200, 300, 400, 500], reverse=True)
</function_calls>

請確保：
- 用戶查詢與函數的用途相關
- 函數參數準確反映用戶查詢中指定的要求
- 所有用戶查詢必須使用繁體中文撰寫
- 人名使用中文名字（例如：王小明、李美玲）
- 地點、公司名稱等也使用中文

生成 {{num_queries}} 個不同的查詢
```
