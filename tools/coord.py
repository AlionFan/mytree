#!/usr/bin/env python3
"""HKS 本机代理消息与编辑范围认领；仅使用 Python 标准库。"""
import argparse
from contextlib import contextmanager
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
NAME = re.compile(r"[a-z][a-z0-9_-]{0,79}\Z")


def now():
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def name(value):
    if not NAME.fullmatch(value):
        raise argparse.ArgumentTypeError("名称使用小写字母开头的字母、数字、- 或 _，最多 80 字符")
    return value


@contextmanager
def transaction(root):
    folder = root / ".coordination"
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    state_path = folder / "state.json"
    with open(folder / "state.lock", "a+", encoding="utf-8") as lock:
        os.chmod(lock.name, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = json.loads(state_path.read_text()) if state_path.exists() else {
            "version": 1, "tasks": {}, "messages": [], "acks": {}
        }
        if (not isinstance(state, dict) or state.get("version") != 1
                or not isinstance(state.get("tasks"), dict)
                or not isinstance(state.get("messages"), list)
                or not isinstance(state.get("acks"), dict)):
            raise ValueError("协作状态格式异常，请保留原文件并核实，不自动覆盖")
        before = json.dumps(state, ensure_ascii=False, sort_keys=True)
        yield state
        if json.dumps(state, ensure_ascii=False, sort_keys=True) != before:
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=folder,
                                                 prefix="state-", suffix=".tmp", delete=False) as output:
                    temporary = output.name
                    os.chmod(temporary, 0o600)
                    json.dump(state, output, ensure_ascii=False, indent=2)
                    output.write("\n")
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, state_path)
            finally:
                if temporary and os.path.exists(temporary):
                    os.unlink(temporary)


def scopes_for(root, values):
    scopes = []
    for value in values:
        if not value or any(char in value for char in "*?[]"):
            raise ValueError("范围必须是具体文件或目录，不能使用 glob")
        target = Path(value)
        if target.is_absolute():
            raise ValueError("范围必须相对于项目根目录")
        try:
            scope = (root / target).resolve().relative_to(root).as_posix()
        except ValueError:
            raise ValueError("范围不能离开项目根目录") from None
        if scope in (".", ".coordination") or scope.startswith(".coordination/"):
            raise ValueError("请认领具体源码或文档范围，不占用根目录或协作状态")
        scopes.append(scope)
    return sorted(set(scopes))


def overlaps(first, second):
    return first == second or first.startswith(second + "/") or second.startswith(first + "/")


def dispatch(args, state, root):
    command = args.command
    if command == "status":
        return {"tasks": list(state["tasks"].values()), "messages": len(state["messages"]),
                "note": "认领是协作约定，不阻止未接入规则的编辑器；消息不自动唤醒会话。"}
    if command == "claim":
        scopes = scopes_for(root, args.scope)
        for requirement in args.req:
            if not re.fullmatch(r"(?:FR|NFR|DEV)-\d{3}", requirement):
                raise ValueError("需求编号格式应为 FR-001、NFR-001 或 DEV-001")
        old = state["tasks"].get(args.task)
        if old and old["agent"] != args.agent:
            raise ValueError("任务编号已属于另一代理，请使用新编号")
        for task in state["tasks"].values():
            if task["status"] != "active" or task["task"] == args.task:
                continue
            for wanted in scopes:
                for occupied in task["scopes"]:
                    if overlaps(wanted, occupied):
                        raise ValueError(f"范围冲突：{wanted} 与 {task['agent']} / {task['task']} 的 {occupied} 重叠；请先交接")
        task = {"task": args.task, "agent": args.agent, "scopes": scopes,
                "requirements": args.req, "status": "active", "updated_at": now()}
        state["tasks"][args.task] = task
        return task
    if command in ("done", "release"):
        task = state["tasks"].get(args.task)
        if not task or task["agent"] != args.agent or task["status"] != "active":
            raise ValueError("只能结束本人当前有效的认领")
        task.update(status="done" if command == "done" else "released", updated_at=now(),
                    summary=args.summary if command == "done" else args.reason)
        return task
    if command == "send":
        if not args.text.strip() or len(args.text) > 8000:
            raise ValueError("消息不能为空且最多 8000 字符")
        message = {"id": len(state["messages"]) + 1, "at": now(), "from": args.sender,
                   "to": args.to, "text": args.text.strip()}
        state["messages"].append(message)
        return message
    if command == "inbox":
        cursor = 0 if args.all else state["acks"].get(args.agent, 0)
        family = args.agent.split("-", 1)[0]
        messages = [item for item in state["messages"]
                    if item["id"] > cursor and item["to"] in (args.agent, family, "all")][:args.limit]
        if args.ack and messages:
            state["acks"][args.agent] = max(state["acks"].get(args.agent, 0), messages[-1]["id"])
        return {"agent": args.agent, "messages": messages, "acked_through": state["acks"].get(args.agent, 0)}
    raise ValueError("未知命令")


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="查看任务及消息数量")
    claim = commands.add_parser("claim", help="原子认领编辑范围，拒绝重叠")
    claim.add_argument("--agent", type=name, required=True)
    claim.add_argument("--task", type=name, required=True)
    claim.add_argument("--scope", nargs="+", required=True)
    claim.add_argument("--req", nargs="+", default=[])
    for command in ("done", "release"):
        finish = commands.add_parser(command, help="结束任务并释放范围")
        finish.add_argument("--agent", type=name, required=True)
        finish.add_argument("--task", type=name, required=True)
        finish.add_argument("--summary" if command == "done" else "--reason", required=True)
    send = commands.add_parser("send", help="发送共享消息，不主动唤醒会话")
    send.add_argument("--from", dest="sender", type=name, required=True)
    send.add_argument("--to", type=name, required=True)
    send.add_argument("--text", required=True)
    inbox = commands.add_parser("inbox", help="查看未读消息，显式 --ack 标记本批已读")
    inbox.add_argument("--agent", type=name, required=True)
    inbox.add_argument("--ack", action="store_true")
    inbox.add_argument("--all", action="store_true")
    inbox.add_argument("--limit", type=int, default=20)
    return result


def main(arguments=None, root=ROOT):
    args = parser().parse_args(arguments)
    if args.command == "inbox" and not 1 <= args.limit <= 200:
        print("--limit 必须在 1–200 之间", file=sys.stderr)
        return 1
    try:
        root = Path(root).resolve()
        with transaction(root) as state:
            output = dispatch(args, state, root)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"协作操作失败：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
