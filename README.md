# 某轮订单路线复盘智能体

本工具用于复盘已经筛选出来的骑手某一轮订单。它读取 BI 导出的订单明细、关键节点截图目录，并可选调用 Google Maps Platform，输出异常时间线和文字结论。

第一版重点做后置复盘辅助，不做自动处罚结论。

## 最简单用法

```bash
./复盘
```

启动后，工具会先把本次需要输入的内容发给你，然后逐项提问。你按提示输入即可。

你可以输入：

- `订单复盘，Google map API是...`：表示开始本轮复盘，并提供本次 API key。
- `复盘结束`：表示本轮信息录入完毕，开始生成报告。

命令行里等价启动方式：

```bash
python3 -m route_review_agent.cli review
```

只看本次需要准备什么：

```bash
python3 -m route_review_agent.cli template
```

## 向导会要求输入什么

每轮订单会要求：

- Google Maps API key：只在本次运行中使用，不写入文件。
- 配送员/骑手ID。
- 配送工具：电动车、摩托车、汽车、自行车、步行。
- 本轮订单数量。
- 每张订单的单号、商家名称、商家 Google 地址、顾客/落点 Google 地址。
- 接单时间、到店时间、点击取餐时间、完成时间。
- 送餐员接这张订单时所在位置：Google 地址、坐标，或截图路径。
- 关键节点截图路径：可多个，用逗号分隔。
- 额外分时段位置截图目录：可留空。

时间支持：

- `2026-06-04 18:30`
- `18:30`
- `18:30:00`

## 结果在哪里

复盘结束后会生成：

- `reports/review_骑手ID_时间.md`：人工可读报告。
- `reports/review_骑手ID_时间.json`：后续聊天追问使用的结构化结果。

继续追问报告：

```bash
python3 -m route_review_agent.cli chat --result reports/生成的结果.json
```

可问：`总结`、`异常时间线`、`高风险`、`证据不足`、`建议核查`。

## 后台排班操作规则

如果要继续使用 Codex 协助处理下周班表、Flushing/BK 区域选择、送餐员编号识别、添加/删除班次、保存并发布等后台操作，请参考：

- `docs/schedule_booking_workflow.md`

## CSV 高级用法

如果之后你想批量处理 BI 表格，也仍然支持 CSV：

```bash
python3 -m route_review_agent.cli analyze \
  --orders examples/sample_orders.csv \
  --screenshots examples/screenshots \
  --out reports/sample_report.md \
  --json-out reports/sample_result.json
```

## 输入 CSV 字段

必填字段：

- `order_id`
- `courier_id`
- `vehicle_type`：`walk`、`bike`、`ebike`、`car`
- `accepted_at`
- `arrived_store_at`
- `picked_up_at`
- `delivered_at`
- `accept_address`
- `pickup_address`
- `dropoff_address`

推荐字段：

- `accept_lat`, `accept_lng`
- `pickup_lat`, `pickup_lng`
- `dropoff_lat`, `dropoff_lng`
- `expected_accept_to_store_min`
- `expected_pickup_to_dropoff_min`

如果没有 Google API key，工具会优先使用 `expected_*` 字段作为地图基准。

## 截图输入

截图目录可选。第一版会尝试调用本机 `tesseract` 做 OCR；如果没有安装，会把截图列为“需人工确认”证据，不阻塞复盘。

建议截图命名包含订单或节点信息，例如：

- `order_1001_accept.png`
- `order_1001_arrived_store.png`
- `order_1001_pickup.png`
- `order_1001_delivered.png`

## 输出结论等级

- `正常`
- `轻微异常`
- `明显异常`
- `证据不足`

工具默认不把“到店后等餐”直接归因给骑手，会标记为“可能受商家影响”。
