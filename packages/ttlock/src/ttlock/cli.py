from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from . import TTLockClient, TTLockConfig, TTLockError

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="TTLock diagnostics (live API calls)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list-locks", help="list owned/shared locks and eKey permissions (sensitive data omitted)")
    listing = commands.add_parser("list-passcodes", help="list passcode metadata")
    listing.add_argument("--show-codes", action="store_true", help="include PIN digits in output")
    for command, help_text in (
        ("generate-timed-pin", "generate a gateway-free code for the current and next UTC hour"),
        ("generate-one-time-pin", "generate a gateway-free single-use code with a six-hour window"),
    ):
        generate = commands.add_parser(command, help=help_text)
        generate.add_argument("--name", default="TTLock CLI generated test")
        generate.add_argument("--passcode-version", type=int, choices=(1, 2, 3, 4), default=4)
    args = parser.parse_args(argv)

    config = TTLockConfig.from_env()
    client = TTLockClient(config)
    try:
        if args.command == "list-passcodes":
            fields = ("lockId", "keyboardPwdId", "keyboardPwdName", "keyboardPwdType", "startDate", "endDate", "status")
            if args.show_codes:
                fields += ("keyboardPwd",)
            output = [{key: row[key] for key in fields if key in row} for row in client.list_passcodes()]
        elif args.command in ("generate-timed-pin", "generate-one-time-pin"):
            single_use = args.command == "generate-one-time-pin"
            kwargs = dict(keyboard_pwd_name=args.name, keyboard_pwd_version=args.passcode_version)
            if single_use:
                result = client.generate_one_time_pin(**kwargs)
            else:
                result = client.generate_timed_pin(**kwargs)
            output = {"keyboardPwdId": result["keyboardPwdId"], "keyboardPwd": result["keyboardPwd"],
                      "lockId": result["lockId"],
                      "startDate": datetime.fromtimestamp(result["startDate"] / 1000, timezone.utc).isoformat(),
                      "endDate": datetime.fromtimestamp(result["endDate"] / 1000, timezone.utc).isoformat(),
                      "keyboardPwdType": 1 if single_use else 3, "singleUse": single_use}
        else:
            # The lock-list API may include lockData and administrative credentials.
            fields = ("lockId", "lockName", "lockAlias", "hasGateway", "electricQuantity",
                        "keyId", "userType", "keyStatus", "keyRight", "remoteEnable", "startDate", "endDate")
            output = [{key: row[key] for key in fields if key in row} for row in client.list_locks()]
    except TTLockError as exc:
        print(json.dumps({"error": exc.code, "uncertain": exc.uncertain}), file=sys.stderr)
        if exc.uncertain:
            print("Creation may have succeeded. Inspect the lock; do not retry blindly.", file=sys.stderr)
        raise SystemExit(1) from None
    except (ValueError, OverflowError):
        print(json.dumps({"error": "invalid_input"}), file=sys.stderr)
        raise SystemExit(2) from None
    print(json.dumps(output, ensure_ascii=False))
