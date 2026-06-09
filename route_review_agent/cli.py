from __future__ import annotations

import argparse
import sys

from .analyzer import analyze_round
from .chat import answer, load_result
from .google_maps import GoogleMapsClient
from .guided import print_input_template, run_guided_review
from .io import collect_screenshot_files, load_orders, write_json
from .ocr import read_screenshots
from .report import render_markdown, write_markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="某轮订单路线复盘智能体")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="分析某一轮订单")
    analyze.add_argument("--orders", required=True, help="订单CSV或JSON路径")
    analyze.add_argument("--screenshots", help="关键节点截图目录")
    analyze.add_argument("--out", help="Markdown报告输出路径")
    analyze.add_argument("--json-out", help="结构化JSON输出路径")
    analyze.add_argument("--google-api-key", help="Google Maps Platform API key")

    chat = sub.add_parser("chat", help="基于分析结果进行聊天式追问")
    chat.add_argument("--result", required=True, help="analyze 生成的JSON结果")
    chat.add_argument("--question", help="直接提问一次后退出")

    sub.add_parser("review", help="中文向导式录入某轮订单并生成复盘报告")
    sub.add_parser("订单复盘", help="中文向导式录入某轮订单并生成复盘报告")
    sub.add_parser("template", help="打印本次复盘需要输入的内容清单")
    return parser


def cmd_analyze(args: argparse.Namespace) -> int:
    orders = load_orders(args.orders)
    screenshot_paths = collect_screenshot_files(args.screenshots)
    screenshots = read_screenshots(screenshot_paths)
    result = analyze_round(orders, screenshots, GoogleMapsClient(args.google_api_key))
    if args.out:
        write_markdown(result, args.out)
    else:
        print(render_markdown(result))
    if args.json_out:
        write_json(result, args.json_out)
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    result = load_result(args.result)
    if args.question:
        print(answer(result, args.question))
        return 0
    print("进入复盘问答。可问：总结 / 异常时间线 / 高风险 / 证据不足 / 建议核查。输入 exit 退出。")
    while True:
        try:
            question = input("> ").strip()
        except EOFError:
            break
        if question.lower() in {"exit", "quit", "q"}:
            break
        if not question:
            continue
        print(answer(result, question))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "analyze":
        return cmd_analyze(args)
    if args.command == "chat":
        return cmd_chat(args)
    if args.command in {"review", "订单复盘"}:
        return run_guided_review()
    if args.command == "template":
        return print_input_template()
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
