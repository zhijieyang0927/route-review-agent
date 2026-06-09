from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .analyzer import analyze_round
from .google_maps import GoogleMapsClient
from .io import collect_screenshot_files, write_json
from .models import Location, Order, normalize_vehicle_type, parse_time
from .ocr import read_screenshots
from .report import write_markdown


INPUT_TEMPLATE = """本次订单复盘需要你逐一提供这些内容：

1. Google Maps API key（可直接粘贴；只在本次运行中使用，不写入文件）
2. 配送员/骑手ID（没有可留空）
3. 配送工具：电动车 / 摩托车 / 汽车 / 自行车 / 步行
4. 本轮订单数量
5. 每张订单：
   - 订单号
   - 商家名称
   - 商家 Google 地址（商家名不好识别时必填）
   - 顾客/落点 Google 地址（如果没有，留空；对应送达阶段会标记证据不足）
   - 接单时间
   - 到店时间
   - 点击取餐时间
   - 完成时间
   - 接单时骑手所在位置：Google 地址、坐标，或截图文件路径
   - 该订单关键节点截图文件路径（可多个，用逗号分隔，可留空）
6. 额外分时段位置截图目录（可留空）

时间支持：2026-06-04 18:30、18:30、18:30:00。
结束词：复盘结束。输入后会生成报告。
"""


def run_guided_review() -> int:
    print("订单复盘已开启。")
    print(INPUT_TEMPLATE)
    api_key = _extract_api_key(_ask("Google map API是", secret=False))
    courier_id = _ask("配送员/骑手ID（可留空）") or "UNKNOWN"
    vehicle_type = normalize_vehicle_type(_ask("配送工具（电动车/摩托车/汽车/自行车/步行）") or "电动车")
    count = _ask_int("本轮订单数量")
    orders: list[Order] = []
    screenshot_inputs: list[str] = []

    for index in range(1, count + 1):
        print(f"\n第 {index} 张订单")
        order_id = _ask("订单号")
        merchant_name = _ask("商家名称")
        pickup_address = _ask("商家 Google 地址（商家名清晰也建议填；可留空）")
        dropoff_address = _ask("顾客/落点 Google 地址（可留空）")
        accepted_at = _ask("接单时间")
        arrived_store_at = _ask("到店时间")
        picked_up_at = _ask("点击取餐时间")
        delivered_at = _ask("完成时间")
        accept_position = _ask("接单时骑手所在位置（Google地址/坐标/截图路径）")
        screenshot_text = _ask("该订单关键节点截图文件路径（多个用逗号分隔，可留空）")
        screenshot_inputs.extend(_split_paths(screenshot_text))

        accept_location = _location_from_free_text("接单位置", accept_position)
        pickup_location = Location(label=merchant_name or "商家/取点", address=pickup_address)
        dropoff_location = Location(label="顾客/落点", address=dropoff_address, needs_confirmation=not bool(dropoff_address))
        orders.append(
            Order(
                order_id=order_id,
                courier_id=courier_id,
                vehicle_type=vehicle_type,
                accepted_at=parse_time(accepted_at),
                arrived_store_at=parse_time(arrived_store_at),
                picked_up_at=parse_time(picked_up_at),
                delivered_at=parse_time(delivered_at),
                accept_location=accept_location,
                pickup_location=pickup_location,
                dropoff_location=dropoff_location,
            )
        )

    extra_screenshots = _ask("额外分时段位置截图目录或文件路径（可留空）")
    screenshot_inputs.extend(_split_paths(extra_screenshots))
    _wait_for_end()

    screenshots = _load_screenshot_evidence(screenshot_inputs)
    result = analyze_round(orders, screenshots, GoogleMapsClient(api_key))
    out_dir = Path("reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"review_{courier_id}_{_stamp(orders[0].accepted_at)}"
    markdown_path = out_dir / f"{stem}.md"
    json_path = out_dir / f"{stem}.json"
    write_markdown(result, markdown_path)
    write_json(result, json_path)

    print("\n复盘结束，已生成：")
    print(f"- Markdown报告：{markdown_path}")
    print(f"- 结构化结果：{json_path}")
    print("\n核心结论：")
    print(result.conclusion)
    if result.recommendations:
        print("\n建议核查：")
        for item in result.recommendations:
            print(f"- {item}")
    return 0


def print_input_template() -> int:
    print(INPUT_TEMPLATE)
    return 0


def _ask(prompt: str, secret: bool = False) -> str:
    del secret
    value = input(f"{prompt}：").strip()
    if value == "复盘结束":
        raise ValueError("还没有录入完整订单，不能提前结束。")
    return value


def _ask_int(prompt: str) -> int:
    while True:
        value = _ask(prompt)
        try:
            number = int(value)
            if number > 0:
                return number
        except ValueError:
            pass
        print("请输入大于 0 的数字。")


def _wait_for_end() -> None:
    while True:
        value = input("\n输入“复盘结束”生成报告：").strip()
        if value == "复盘结束":
            return
        print("如果还有额外内容，请先在前面的截图路径中填写；这里请输入“复盘结束”。")


def _split_paths(text: str) -> list[str]:
    if not text:
        return []
    normalized = text.replace("，", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def _load_screenshot_evidence(inputs: list[str]):
    paths = []
    for item in inputs:
        path = Path(item).expanduser()
        if path.is_dir():
            paths.extend(collect_screenshot_files(path))
        elif path.exists():
            paths.append(path)
    return read_screenshots(paths)


def _location_from_free_text(label: str, text: str) -> Location:
    text = (text or "").strip()
    lat_lng = _parse_lat_lng(text)
    if lat_lng:
        lat, lng = lat_lng
        return Location(label=label, lat=lat, lng=lng)
    if _looks_like_image_path(text):
        return Location(label=label, address="", source=f"screenshot:{text}", needs_confirmation=True)
    return Location(label=label, address=text, needs_confirmation=not bool(text))


def _parse_lat_lng(text: str) -> tuple[float, float] | None:
    normalized = text.replace("，", ",")
    parts = [part.strip() for part in normalized.split(",")]
    if len(parts) != 2:
        return None
    try:
        lat = float(parts[0])
        lng = float(parts[1])
    except ValueError:
        return None
    if -90 <= lat <= 90 and -180 <= lng <= 180:
        return lat, lng
    return None


def _looks_like_image_path(text: str) -> bool:
    suffixes = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff")
    return text.lower().endswith(suffixes)


def _extract_api_key(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    match = re.search(r"(?:api\s*是|api\s*key\s*是|api=|key=|是)\s*([A-Za-z0-9_\-]+)", text, re.IGNORECASE)
    if match:
        return match.group(1)
    return text


def _stamp(value) -> str:
    if getattr(value, "year", None) == 1900:
        today = datetime.now()
        value = value.replace(year=today.year, month=today.month, day=today.day)
    return value.strftime("%Y%m%d_%H%M")
